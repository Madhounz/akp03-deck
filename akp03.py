"""
Driver for the Ajazz AKP03E (and Mirabox N3 / AKP03 clones).

Layout
  keys 0..5   LCD keys (60x60 images)
  keys 6..8   round buttons
  knobs 0..2  rotary encoders (0 = left small, 1 = big, 2 = right small)

Why this design (freeze fixes):
  * ONE thread owns the USB handle. It does every write and read, so two parts of the app
    can never talk to the device at the same time.
  * Images are queued "latest only" per key and capped per second, so the deck is never flooded.
  * Identical images are skipped.
  * Input callbacks run on their own thread, so a slow action can never block USB reads.
  * A watchdog notices when the device stops responding and the app reconnects by itself.

Protocol (mirajazz v3), based on open source work in
  github.com/4ndv/mirajazz, pypi soomfon, github.com/sepivip/codexdeck
"""
from __future__ import annotations

import hashlib
import io
import logging
import queue
import threading
import time
from typing import Callable, Optional

import hid  # pip install hidapi
from PIL import Image

log = logging.getLogger("deck")

KNOWN_IDS = [
    (0x0300, 0x3002),  # Ajazz AKP03E
    (0x0300, 0x1003),  # Ajazz AKP03R
    (0x0300, 0x3003),  # AKP03R rev2
    (0x1500, 0x3001),  # AKP03E/R rev2, Mirabox N3 rev2, Soomfon SE
    (0x6602, 0x1002),  # Mirabox N3 (older)
]

PACKET = 1024
IMG_SIZE = 60
JPEG_QUALITY = 95
JPEG_SUBSAMPLING = 0  # 0 = 4:4:4 (sharpest), 2 = 4:2:0 (safe fallback)
MAX_IMAGES_PER_SEC = 24   # flow control: what the deck can comfortably take
KEEPALIVE_S = 8
STALL_S = 4.0             # no successful I/O for this long while work is waiting = stalled

CRT = b"\x43\x52\x54\x00\x00"
ACK = b"\x41\x43\x4b"
LCD_KEYS, BUTTONS, KNOBS = 6, 3, 3

_BUTTON_IDS = {0x25: 6, 0x30: 7, 0x31: 8}
_KNOB_PRESS = {0x33: 0, 0x35: 1, 0x34: 2}
_KNOB_TURN = {0x90: (0, -1), 0x91: (0, +1), 0x50: (1, -1), 0x51: (1, +1), 0x60: (2, -1), 0x61: (2, +1)}


def _cmd(*tail) -> bytes:
    body = CRT
    for t in tail:
        body += t if isinstance(t, (bytes, bytearray)) else bytes([t])
    return b"\x00" + body.ljust(PACKET, b"\x00")


def find_devices() -> list[dict]:
    found = []
    for vid, pid in KNOWN_IDS:
        found += hid.enumerate(vid, pid)
    found.sort(key=lambda d: 0 if d.get("usage_page", 0) >= 0xFF00 else 1)
    return found


def list_all_hid() -> list[str]:
    out = []
    for d in hid.enumerate():
        out.append(f"{d['vendor_id']:04x}:{d['product_id']:04x}  page={d.get('usage_page', 0):04x}  "
                   f"{d.get('manufacturer_string') or ''} {d.get('product_string') or ''}")
    return sorted(set(out))


def encode(image: Image.Image) -> bytes:
    img = image.convert("RGB")
    if img.size != (IMG_SIZE, IMG_SIZE):
        img = img.resize((IMG_SIZE, IMG_SIZE), Image.LANCZOS)
    img = img.transpose(Image.ROTATE_270)  # the panel is mounted rotated
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY, subsampling=JPEG_SUBSAMPLING)
    return buf.getvalue()


class Deck:
    def __init__(self, info: dict):
        self.info = info
        self._dev = hid.device()
        self._dev.open_path(info["path"])
        self._cv = threading.Condition()
        self._cmds: list[bytes] = []
        self._imgs: dict[int, tuple[bytes, str]] = {}
        self._sent: dict[int, str] = {}
        self._events: queue.Queue = queue.Queue()
        self._alive = False
        self._dead = False
        self.last_ok = time.time()
        self.beat = time.time()   # updated every pass of the I/O loop
        self.stats = {"images": 0, "skipped": 0, "errors": 0}
        self.on_key: Optional[Callable[[int, bool], None]] = None
        self.on_knob_turn: Optional[Callable[[int, int], None]] = None
        self.on_knob_press: Optional[Callable[[int, bool], None]] = None
        self.on_disconnect: Optional[Callable[[], None]] = None
        self._queue_cmd(_cmd(b"DIS"))
        self._queue_cmd(_cmd(b"LIG", 0, 0, 0))

    @classmethod
    def open_first(cls) -> "Deck":
        devs = find_devices()
        if not devs:
            raise RuntimeError("AKP03E not found")
        return cls(devs[0])

    @property
    def id_string(self) -> str:
        return f"{self.info['vendor_id']:04X}:{self.info['product_id']:04X}"

    # ---------- public API: every call only queues work, never touches USB ----------
    def _queue_cmd(self, pkt: bytes):
        with self._cv:
            self._cmds.append(pkt)
            self._cv.notify()

    def set_brightness(self, pct: int):
        self._queue_cmd(_cmd(b"LIG", 0, 0, max(0, min(100, int(pct)))))

    def set_key_image(self, key: int, image: Image.Image):
        if not 0 <= key < LCD_KEYS or self._dead:
            return
        data = encode(image)
        h = hashlib.blake2b(data, digest_size=8).hexdigest()
        with self._cv:
            if self._sent.get(key) == h and key not in self._imgs:
                self.stats["skipped"] += 1
                return
            self._imgs[key] = (data, h)  # newer image replaces a waiting one
            self._cv.notify()

    def clear_all(self):
        with self._cv:
            self._imgs.clear()
            self._sent.clear()
            self._cmds += [_cmd(b"CLE", 0, 0, 0, 0xFF), _cmd(b"STP")]
            self._cv.notify()

    def pending(self) -> int:
        with self._cv:
            return len(self._imgs) + len(self._cmds)

    def start(self):
        if self._alive:
            return
        self._alive = True
        threading.Thread(target=self._io_loop, name="deck-io", daemon=True).start()
        threading.Thread(target=self._event_loop, name="deck-events", daemon=True).start()

    # ---------- the one thread that talks to USB ----------
    def _io_loop(self):
        min_gap = 1.0 / MAX_IMAGES_PER_SEC
        last_img = 0.0
        last_keep = time.time()
        try:
            while self._alive:
                self.beat = time.time()
                with self._cv:
                    cmds, self._cmds = self._cmds, []
                    img = None
                    if self._imgs and time.time() - last_img >= min_gap:
                        k = next(iter(self._imgs))
                        img = (k, *self._imgs.pop(k))
                for pkt in cmds:
                    self._dev.write(pkt)
                    self.last_ok = time.time()
                if img:
                    k, data, h = img
                    n = len(data)
                    self._dev.write(_cmd(b"BAT", 0, 0, (n >> 8) & 0xFF, n & 0xFF, k + 1))
                    for off in range(0, n, PACKET):
                        self._dev.write(b"\x00" + data[off:off + PACKET].ljust(PACKET, b"\x00"))
                    self._dev.write(_cmd(b"STP"))
                    self._sent[k] = h
                    self.stats["images"] += 1
                    last_img = self.last_ok = time.time()
                if time.time() - last_keep > KEEPALIVE_S:
                    self._dev.write(_cmd(b"CONNECT"))
                    last_keep = self.last_ok = time.time()
                busy = bool(self._imgs or self._cmds)
                data = self._dev.read(512, 5 if busy else 40)
                if data:
                    self.last_ok = time.time()
                    if len(data) >= 11:
                        self._events.put(bytes(data))
        except Exception as e:
            self.stats["errors"] += 1
            log.warning("Deck I/O error: %s", e)
            self._fail()

    def _event_loop(self):
        while self._alive:
            try:
                data = self._events.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self._dispatch(data)
            except Exception as e:
                log.exception("Input handler error: %s", e)

    def stalled(self) -> bool:
        """True when the I/O loop is stuck inside a USB call, or work waits and nothing gets through."""
        if not self._alive:
            return False
        now = time.time()
        return now - self.beat > STALL_S or (self.pending() > 0 and now - self.last_ok > STALL_S)

    def _fail(self):
        if self._dead:
            return
        self._dead = True
        self._alive = False
        try:
            self._dev.close()
        except Exception:
            pass
        if self.on_disconnect:
            threading.Thread(target=self.on_disconnect, daemon=True).start()

    def _dispatch(self, data: bytes):
        if data[:3] != ACK:
            return
        code, state = data[9], data[10]
        pressed = state != 0
        if 1 <= code <= LCD_KEYS:
            self.on_key and self.on_key(code - 1, pressed)
        elif code in _BUTTON_IDS:
            self.on_key and self.on_key(_BUTTON_IDS[code], pressed)
        elif code in _KNOB_PRESS:
            self.on_knob_press and self.on_knob_press(_KNOB_PRESS[code], pressed)
        elif code in _KNOB_TURN:
            knob, delta = _KNOB_TURN[code]
            self.on_knob_turn and self.on_knob_turn(knob, delta)

    def close(self, clear=True):
        if clear and self._alive:
            self.clear_all()
            end = time.time() + 1.0
            while self.pending() and time.time() < end:
                time.sleep(0.02)
        self._alive = False
        self._dead = True
        time.sleep(0.1)
        try:
            self._dev.close()
        except Exception:
            pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    devs = find_devices()
    if not devs:
        print("Deck not found. All HID devices:")
        print("\n".join(list_all_hid()))
        raise SystemExit(1)
    deck = Deck(devs[0])
    print("Connected:", deck.id_string)
    deck.set_brightness(80)
    for i, c in enumerate(["red", "orange", "yellow", "green", "blue", "purple"]):
        deck.set_key_image(i, Image.new("RGB", (60, 60), c))
    deck.on_key = lambda k, p: print(f"key {k} {'down' if p else 'up'}")
    deck.on_knob_turn = lambda k, d: print(f"knob {k} turn {d:+d}")
    deck.on_knob_press = lambda k, p: print(f"knob {k} {'down' if p else 'up'}")
    deck.start()
    print("Press keys / turn knobs. Ctrl+C to quit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        deck.close()
