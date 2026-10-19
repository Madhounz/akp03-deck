"""The brain: config, pages, device, gestures, live tiles, knob modes, smart pages, games, stats."""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import queue
import random
import shutil
import threading
import time

import actions
import akp03
import context
import icons
import library
import render
from media import Audio, Brightness, NowPlaying, Outlook
from monitor import Monitor, METRICS

HERE = os.path.dirname(os.path.abspath(__file__))
log = logging.getLogger("core")
CONFIG_PATH = os.path.join(HERE, "config.json")
SECRET_PATH = os.path.join(HERE, "secret.json")

HOLD_S = 0.45      # press longer than this = hold
DOUBLE_S = 0.28    # second tap within this = double tap
HUD_S = 1.6        # how long the knob dashboard stays up

# knob modes: id -> (name, 3D icon)
KNOB_MODES = {
    "volume": ("Volume", "speaker_high_volume"),
    "app_media": ("Music volume", "musical_note"),
    "app_focus": ("Active app", "speaker_medium_volume"),
    "brightness": ("Brightness", "sun"),
    "scroll": ("Scroll", "computer_mouse"),
    "scrub": ("Seek", "fast_forward_button"),
    "zoom": ("Zoom", "magnifying_glass_tilted_left"),
    "pages": ("Pages", "bookmark_tabs"),
    "tracks": ("Tracks", "next_track_button"),
}
EXTRA_LIVE = [("nowplaying", "Now playing"), ("timer", "Focus timer"), ("mic", "Microphone")]


def data_url(img) -> str:
    buf = io.BytesIO()
    try:
        img.convert("RGB").save(buf, format="WEBP", quality=88, method=3)
        mime = "webp"
    except Exception:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        mime = "png"
    return f"data:image/{mime};base64," + base64.b64encode(buf.getvalue()).decode()


class Core:
    def __init__(self):
        self.lock = threading.RLock()
        self.cfg = self._load()
        self.secret = self._load_secret()
        self.deck: akp03.Deck | None = None
        self._listeners: list[queue.Queue] = []
        self._gen = 0
        self._busy = False
        self.monitor = Monitor()
        self.audio = Audio()
        self.bright = Brightness()
        self.np = NowPlaying()
        self.outlook = Outlook()
        self.monitor.wanted = self.wanted_live
        self.np.wanted = lambda: "nowplaying" in self.wanted_live()
        self.timer = {"total": self.cfg.get("timer_minutes", 25) * 60.0, "remaining": self.cfg.get("timer_minutes", 25) * 60.0,
                      "running": False, "done": False, "end": 0.0}
        self._down: dict = {}
        self._held: set = set()
        self._tap_timers: dict = {}
        self._overlay: dict = {}
        self._due: dict = {}
        self._studio_due: dict = {}
        self._hud_until = 0.0
        self._hud_on = False
        self._hud_state = None
        self._hud_ev = threading.Event()
        self.game = None
        self.party = False
        self._auto = None
        self._last_fg = ""
        self._stats_dirty = False
        self.health = {"state": "searching", "reconnects": 0, "since": time.time(), "last_error": ""}
        self.flyout_open = False
        for target in (self._connect_loop, self._anim_loop, self._smart_loop, self._stats_loop, self._hud_loop, self._auto_icons):
            threading.Thread(target=target, daemon=True).start()

    # ---------------- config ----------------
    def _load(self) -> dict:
        cfg = None
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, encoding="utf-8") as f:
                    cfg = json.load(f)
                if "pages" not in cfg:
                    shutil.copy2(CONFIG_PATH, os.path.join(HERE, "config.v2-backup.json"))
                    cfg = None
            except Exception as e:
                print("Bad config.json, using defaults:", e)
                cfg = None
        if cfg is None:
            cfg = library.default_config()
        if cfg.get("version", 3) < 4:
            names = {p.get("name", "").lower() for p in cfg.get("pages", [])}
            if "gaming" not in names:
                cfg["pages"].append(library.gaming_page())
            if "system" not in names:
                cfg["pages"].append(library.system_page())
        if cfg.get("version", 3) < 5:
            shutil.copy2(CONFIG_PATH, os.path.join(HERE, "config.v4-backup.json")) if os.path.exists(CONFIG_PATH) else None
            cfg = library.upgrade_v5(cfg)
        d = library.default_config()
        for k in ("brightness", "splash", "buttons", "knobs", "smart", "stats", "timer_minutes"):
            cfg.setdefault(k, d[k])
        for p in cfg["pages"]:
            p.setdefault("keys", {})
            p.setdefault("apps", [])
            for i in range(6):
                p["keys"].setdefault(str(i), library.blank_key())
        for i in range(3):
            cfg["buttons"].setdefault(str(i), {"label": "", "action": {"type": "none", "value": ""}})
            cfg["knobs"].setdefault(str(i), {"label": "", "left": {}, "right": {}, "press": {}})
        cfg["current_page"] = max(0, min(int(cfg.get("current_page", 0)), len(cfg["pages"]) - 1))
        return cfg

    def save(self):
        with self.lock:
            tmp = CONFIG_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.cfg, f, indent=2, ensure_ascii=False)
            os.replace(tmp, CONFIG_PATH)

    def _load_secret(self) -> dict:
        try:
            with open(SECRET_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save_secret(self):
        with open(SECRET_PATH, "w", encoding="utf-8") as f:
            json.dump(self.secret, f)

    def reset(self):
        with self.lock:
            stats = self.cfg.get("stats")
            self.cfg = library.default_config()
            if stats:
                self.cfg["stats"] = stats
            self.save()
        self.push_page(splash=True)
        self.emit({"t": "reload"})

    @property
    def page_index(self) -> int:
        return self.cfg["current_page"]

    def accent(self) -> str:
        return self.cfg["pages"][self.page_index].get("accent", "#7c5cff")

    # ---------------- events to the studio ----------------
    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        self._listeners.append(q)
        return q

    def unsubscribe(self, q):
        if q in self._listeners:
            self._listeners.remove(q)

    def emit(self, ev: dict):
        for q in list(self._listeners):
            q.put(ev)

    def toast(self, msg: str, err=False):
        self.emit({"t": "toast", "msg": msg, "err": err})

    # ---------------- live data for tiles ----------------
    def get(self, kind: str) -> dict:
        if kind == "nowplaying":
            i = self.np.info
            return {"style": "np", **i, "ok": self.np.ok}
        if kind == "timer":
            return {"style": "timer", **self.timer}
        if kind == "mic":
            return {"style": "mic", "muted": self.audio.mic_muted()}
        return self.monitor.get(kind)

    def summary(self, kinds) -> dict:
        out = {}
        rest = []
        for k in kinds:
            if k == "nowplaying":
                i = self.np.info
                out[k] = (f"{i['title']} by {i['artist']}" if i.get("artist") else i["title"]) if i.get("title") else "Nothing playing"
            elif k == "timer":
                m, s = divmod(int(self.timer["remaining"] + 0.99), 60)
                out[k] = "Done" if self.timer["done"] else f"{m}:{s:02d}"
            elif k == "mic":
                v = self.audio.mic_muted()
                out[k] = "Muted" if v else ("Live" if v is False else "--")
            else:
                rest.append(k)
        out.update(self.monitor.summary(rest))
        return out

    def metrics_list(self):
        return [{"id": m[0], "name": m[1]} for m in METRICS] + [{"id": a, "name": b} for a, b in EXTRA_LIVE]

    def monitor_status(self):
        st = self.monitor.status()
        st["available"].update({"nowplaying": self.np.ok, "timer": True, "mic": self.audio.ok})
        st.update(audio=self.audio.ok, media=self.np.ok, brightness=self.bright.sbc is not None)
        return st

    # ---------------- images ----------------
    def _badge(self, k):
        b = k.get("badge")
        if b == "outlook":
            self.outlook.wanted = True
            return {"count": self.outlook.count} if self.outlook.count else None
        if b == "mic":
            return {"muted": True} if self.audio.mic_muted() else None
        return None

    def key_image(self, p: int, i: int, size: int, device=False, t=None):
        now = time.time()
        if p == self.page_index:
            if self.party:
                return render.rainbow_tile(i, now, size)
            ov = self._overlay.get(i)
            if ov and now < ov["until"]:
                return self._overlay_image(ov, now, size)
        page = self.cfg["pages"][p]
        k = page["keys"][str(i)]
        tiles = render.wallpaper_tiles(page.get("wallpaper", ""), size)
        return render.render_key(k, size, device, tiles[i] if tiles else None, mon=self,
                                 accent=page.get("accent", "#7c5cff"), t=t if t is not None else now, badge=self._badge(k))

    def _overlay_image(self, ov, now, size):
        kind = ov["kind"]
        if kind == "dice":
            v = random.randint(1, 6) if now < ov["roll_until"] else ov["value"]
            return render.overlay_tile("dice", now, value=v, size=size)
        if kind == "coin":
            return render.overlay_tile("coin", now, value=None if now < ov["roll_until"] else ov["value"], size=size)
        return render.overlay_tile(kind, now - ov.get("t0", now), self.accent(), ov.get("text", ""), size=size)

    def previews(self, p: int) -> list[str]:
        return [data_url(self.key_image(p, i, 192)) for i in range(6)]

    def wanted_live(self) -> set:
        """Live data that someone is looking at right now (deck page, studio or flyout)."""
        keys = self.cfg["pages"][self.page_index]["keys"]
        kinds = {k.get("live") for k in keys.values() if k.get("live")}
        if self._listeners or self.flyout_open:
            kinds |= {"cpu_usage", "ram", "nowplaying"}
        return kinds

    def live_keys(self, p: int) -> list[int]:
        keys = self.cfg["pages"][p]["keys"]
        return [i for i in range(6) if keys[str(i)].get("live")]

    # ---------------- device output ----------------
    def push_key(self, p: int, i: int):
        d = self.deck
        if d and p == self.page_index and not self.game:
            img = self.key_image(p, i, 60, device=True)
            threading.Thread(target=self._upload, args=(d, i, img), daemon=True).start()

    @staticmethod
    def _upload(d, i, img):
        try:
            d.set_key_image(i, img)
        except Exception as e:
            print("Upload failed:", e)

    def push_page(self, splash=False, credits=False):
        self._gen += 1
        threading.Thread(target=self._push_page_worker, args=(self._gen, splash, credits), daemon=True).start()

    def _push_page_worker(self, gen, splash, credits=False):
        d = self.deck
        if not d:
            return
        p = self.page_index
        self._busy = True
        try:
            if credits and self.cfg.get("splash", True):
                for i, t in enumerate(render.credit_tiles(library.AUTHOR, library.STUDIO)):
                    d.set_key_image(i, t)
                time.sleep(1.8)
                if gen != self._gen:
                    return
            if splash and self.cfg.get("splash", True):
                tiles = render.splash_tiles(self.cfg["pages"][p], p, len(self.cfg["pages"]))
                for i, t in enumerate(tiles):
                    if gen != self._gen:
                        return
                    d.set_key_image(i, t)
                time.sleep(0.7)
            for i in range(6):
                if gen != self._gen:
                    return
                d.set_key_image(i, self.key_image(p, i, 60, device=True))
        except Exception as e:
            print("Page upload failed:", e)
        finally:
            if gen == self._gen:
                self._busy = False
                self._due.clear()

    def show_tiles(self, tiles):
        """Used by games: put 6 images on the deck and mirror them in the studio."""
        d = self.deck
        if d:
            for i, t in enumerate(tiles):
                try:
                    d.set_key_image(i, t)
                except Exception:
                    pass
        if self._listeners:
            self.emit({"t": "live", "page": self.page_index, "previews": {i: data_url(t) for i, t in enumerate(tiles)}})

    def goto_page(self, p: int, splash=True, auto=False):
        with self.lock:
            p = max(0, min(p, len(self.cfg["pages"]) - 1))
            changed = p != self.page_index
            self.cfg["current_page"] = p
            self.save()
        if not auto:
            self._auto = None
        self._overlay.clear()
        self.party = False
        self.push_page(splash=splash and changed)
        self.emit({"t": "page", "page": p})

    def set_brightness(self, v: int):
        self.cfg["brightness"] = int(v)
        if self.deck:
            try:
                self.deck.set_brightness(int(v))
            except Exception:
                pass

    # ---------------- overlays on a key ----------------
    def overlay(self, i, kind, secs=1.5, **kw):
        if i is None:
            return
        self._overlay[i] = {"kind": kind, "until": time.time() + secs, "t0": time.time(), **kw}
        self._due.pop(i, None)

    # ---------------- actions ----------------
    def run_action(self, a: dict | None, slot=None, wait=False):
        if not a or a.get("type", "none") == "none":
            return
        t, v = a.get("type"), str(a.get("value", "")).strip()
        key_i = slot[1] if slot and slot[0] == "key" else None
        if t == "page":
            self._page_action(v.lower())
        elif t == "timer":
            self._timer_action(v or "toggle")
        elif t == "mic":
            if self.audio.mic_toggle() is None:
                actions.run({"type": "hotkey", "value": "win+alt+k"})
            self._due.clear()
        elif t == "np":
            fn = {"toggle": self.np.toggle, "next": self.np.next, "previous": self.np.previous}.get(v, self.np.toggle)
            if not fn():
                actions.run({"type": "media", "value": {"toggle": "play_pause"}.get(v, v)})
            self._due.clear()
        elif t == "ai":
            threading.Thread(target=self._ai, args=(a, key_i), daemon=True).start()
        elif t == "game":
            self.start_game(v)
        elif t == "fun":
            self._fun(v, key_i)
        elif t == "macro":
            th = threading.Thread(target=self._macro, args=(a.get("steps", []), slot), daemon=True)
            th.start()
            if wait:
                th.join()
        elif t == "wait":
            time.sleep(max(0, min(10000, int(v or 0))) / 1000)
        elif wait:
            actions.run(a)
        else:
            threading.Thread(target=actions.run, args=(a,), daemon=True).start()

    def _page_action(self, v):
        pages = self.cfg["pages"]
        cycle = [i for i, p in enumerate(pages) if not p.get("hidden")] or list(range(len(pages)))
        cur = self.page_index
        if v in ("next", "+", "", "prev", "previous", "back", "-"):
            step = -1 if v in ("prev", "previous", "back", "-") else 1
            if cur in cycle:
                target = cycle[(cycle.index(cur) + step) % len(cycle)]
            else:
                target = self._auto["return"] if self._auto else cycle[0]
        elif v.isdigit():
            target = int(v) - 1
        else:
            names = [p.get("name", "").lower() for p in pages]
            target = names.index(v) if v in names else cur
        self.goto_page(target)

    def _macro(self, steps, slot):
        for st in steps or []:
            self.run_action(st, slot, wait=True)
            time.sleep(0.06)

    def _fun(self, v, i):
        now = time.time()
        if v == "dice":
            self.overlay(i, "dice", 4.0, roll_until=now + 0.9, value=random.randint(1, 6))
        elif v == "coin":
            self.overlay(i, "coin", 4.0, roll_until=now + 1.1, value=random.choice(["HEADS", "TAILS"]))
        elif v == "party":
            self.party = not self.party
            if not self.party:
                self.push_page()

    # ---------------- focus timer ----------------
    def _timer_action(self, v):
        tm, now = self.timer, time.time()
        base = self.cfg.get("timer_minutes", 25) * 60.0
        if v == "reset" or (v == "toggle" and tm["done"]):
            tm.update(total=base, remaining=base, running=False, done=False)
        elif v == "start" or (v == "toggle" and not tm["running"]):
            tm.update(running=True, done=False, end=now + tm["remaining"])
        elif v == "toggle":
            tm.update(running=False, remaining=max(0.0, tm["end"] - now))
        elif v == "add5":
            tm["total"] += 300
            tm["remaining"] += 300
            tm["end"] += 300
            tm["done"] = False
        elif v.startswith("set:"):
            m = float(v[4:] or 25) * 60
            tm.update(total=m, remaining=m, running=False, done=False)
        self._due.clear()

    def _timer_tick(self):
        tm = self.timer
        if tm["running"]:
            tm["remaining"] = max(0.0, tm["end"] - time.time())
            if tm["remaining"] <= 0:
                tm.update(running=False, done=True)
                self.toast("Focus time is up. Nice work!")
                threading.Thread(target=self._alarm, daemon=True).start()

    def _alarm(self):
        d = self.deck
        if not d or self.game:
            return
        self._busy = True
        try:
            for _ in range(3):
                for i, t in enumerate(render.banner([("time's", 0, 0.4), ("up", 1, 0.5)], "#ef4444", rgb=True)):
                    d.set_key_image(i, t)
                time.sleep(0.6)
                for i in range(6):
                    d.set_key_image(i, render.overlay_tile("msg", 0, "#ef4444", ""))
                time.sleep(0.25)
        finally:
            self._busy = False
            self.push_page()

    # ---------------- AI ----------------
    def _ai(self, a, i):
        import ai
        mode = str(a.get("value") or "fix")
        key = self.secret.get("api_key", "")
        if not key:
            self.overlay(i, "msg", 2.2, text="ADD\nKEY")
            self.toast("Add your Claude API key in Settings to use AI keys.", True)
            return
        self.overlay(i, "spin", 60)
        try:
            from pynput.keyboard import Key
            text, _before = ai.grab_selection(actions.kb, Key)
            if not text.strip():
                self.overlay(i, "msg", 2.2, text="SELECT\nTEXT")
                self.toast("Select some text first, then press the AI key.", True)
                return
            out = ai.ask(key, self.secret.get("model", ""), mode, text, a.get("prompt", ""))
            name, _, paste_back = ai.MODES.get(mode, ai.MODES["fix"])
            if paste_back:
                ai.paste(out, actions.kb, Key)
                self.overlay(i, "ok", 1.6, text="DONE")
            else:
                import pyperclip
                pyperclip.copy(out)
                self.overlay(i, "ok", 1.6, text="COPIED")
            self.emit({"t": "ai", "mode": name, "text": out})
        except Exception as e:
            self.overlay(i, "msg", 2.5, text="ERROR")
            self.toast(str(e)[:200], True)

    # ---------------- games ----------------
    def start_game(self, name):
        import games
        if self.game or name not in games.GAMES:
            return
        if not self.deck:
            self.toast("Plug in your deck to play.", True)
            return
        self._gen += 1
        self.party = False
        self.game = games.GAMES[name](self)
        self.emit({"t": "game", "on": True, "name": name})
        self.game.start()

    def stop_game(self):
        if self.game:
            self.game.stop()

    def end_game(self, g):
        if self.game is g:
            self.game = None
            self.emit({"t": "game", "on": False})
            self.push_page()

    # ---------------- gestures (tap, double tap, hold) ----------------
    def _slot_cfg(self, slot):
        kind, i = slot
        if kind == "key":
            return self.cfg["pages"][self.page_index]["keys"].get(str(i), {})
        if kind == "button":
            return self.cfg["buttons"].get(str(i), {})
        return self.cfg["knobs"].get(str(i), {})

    def _valid(self, a):
        return bool(a) and a.get("type", "none") != "none"

    def _down_evt(self, slot):
        self._down[slot] = time.time()
        self._held.discard(slot)
        c = self._slot_cfg(slot)
        hold = c.get("hold") if slot[0] != "knob" or not c.get("modes") else {"type": "_mode_alt"}
        if self._valid(hold):
            token = self._down[slot]
            threading.Timer(HOLD_S, self._hold_check, args=(slot, token, hold)).start()

    def _hold_check(self, slot, token, hold):
        if self._down.get(slot) == token:  # still down
            self._held.add(slot)
            self._fire(slot, "hold", hold)

    def _up_evt(self, slot):
        self._down.pop(slot, None)
        if slot in self._held:
            self._held.discard(slot)
            return
        c = self._slot_cfg(slot)
        tap = c.get("press") if slot[0] == "knob" else c.get("action")
        if slot[0] == "knob" and c.get("modes"):
            tap = {"type": "_mode_next"}
        if self._valid(c.get("double")):
            tmr = self._tap_timers.pop(slot, None)
            if tmr:
                tmr.cancel()
                self._fire(slot, "double", c.get("double"))
            else:
                t = threading.Timer(DOUBLE_S, self._single, args=(slot, tap))
                self._tap_timers[slot] = t
                t.start()
        else:
            self._fire(slot, "tap", tap)

    def _single(self, slot, tap):
        self._tap_timers.pop(slot, None)
        self._fire(slot, "tap", tap)

    def _fire(self, slot, gesture, a):
        kind, i = slot
        c = self._slot_cfg(slot)
        key = f"p{self.page_index}:k{i}" if kind == "key" else (f"b{i}" if kind == "button" else f"n{i}")
        st = self.cfg.setdefault("stats", {}).setdefault("presses", {})
        st[key] = st.get(key, 0) + 1
        self._stats_dirty = True
        self.emit({"t": "press", "kind": kind, "idx": i, "name": c.get("label", ""), "gesture": gesture})
        if a and a.get("type") == "_mode_next":
            return self._mode_next(i)
        if a and a.get("type") == "_mode_alt":
            return self._mode_alt(i)
        self.run_action(a, slot)

    # ---------------- device input ----------------
    def _on_key(self, key: int, pressed: bool):
        slot = ("key", key) if key < 6 else ("button", key - 6)
        if self.game:
            if pressed:
                self.game.press(key) if key < 6 else self.stop_game()
            return
        if self.party and pressed:
            self.party = False
            self.push_page()
            return
        (self._down_evt if pressed else self._up_evt)(slot)

    def _on_knob_press(self, knob: int, pressed: bool):
        if self.game:
            if pressed:
                self.stop_game()
            return
        (self._down_evt if pressed else self._up_evt)(("knob", knob))

    def _on_knob_turn(self, knob: int, delta: int):
        if self.game:
            return
        kn = self.cfg["knobs"].get(str(knob), {})
        self.emit({"t": "turn", "idx": knob, "delta": delta, "name": kn.get("label", "")})
        st = self.cfg.setdefault("stats", {}).setdefault("presses", {})
        st[f"t{knob}"] = st.get(f"t{knob}", 0) + 1
        self._stats_dirty = True
        modes = kn.get("modes") or []
        if modes:
            return self._mode_turn(knob, modes[kn.get("mode", 0) % len(modes)], delta)
        self.run_action(kn.get("right") if delta > 0 else kn.get("left"))

    # ---------------- knob modes + dashboard ----------------
    def _mode_meta(self, mode):
        if mode.startswith("app:"):
            return mode[4:].replace(".exe", "").title(), "speaker_high_volume"
        return KNOB_MODES.get(mode, (mode.title(), "gear"))

    def _mode_value(self, mode, delta=0):
        """Apply a turn and return (frac or None, text, title override)."""
        if mode == "volume":
            v = self.audio.master(delta * 0.02)
            if v is None:
                if delta:
                    actions.run({"type": "media", "value": "volume_up" if delta > 0 else "volume_down"})
                return None, ("louder" if delta > 0 else "quieter") if delta else "turn me", None
            return v, f"{round(v * 100)}%", None
        if mode in ("app_media", "app_focus") or mode.startswith("app:"):
            exe = self.np.app_exe() if mode == "app_media" else (context.foreground()[0] if mode == "app_focus" else mode[4:])
            v, name = self.audio.app(exe, delta * 0.03)
            nice = (name or exe or "App").replace(".exe", "").title()
            if v is None:
                return None, "no sound", nice
            return v, f"{round(v * 100)}%", nice
        if mode == "brightness":
            v = self.bright.change(delta * 5) if delta else (self.bright._v if self.bright._v is not None else self.bright.change(0))
            return (None, "n/a", None) if v is None else (v / 100, f"{v}%", None)
        if delta:
            if mode == "scroll":
                actions.run({"type": "scroll", "value": str(3 * delta)})
            elif mode == "scrub":
                actions.run({"type": "hotkey", "value": "right" if delta > 0 else "left"})
            elif mode == "zoom":
                actions.run({"type": "hotkey", "value": "ctrl+plus" if delta > 0 else "ctrl+minus"})
            elif mode == "pages":
                self._page_action("next" if delta > 0 else "prev")
                return None, "", None
            elif mode == "tracks":
                self.run_action({"type": "np", "value": "next" if delta > 0 else "previous"})
        text = {"scroll": "up" if delta > 0 else "down", "scrub": "+5s" if delta > 0 else "-5s",
                "zoom": "in" if delta > 0 else "out", "tracks": "next" if delta > 0 else "back"}.get(mode, "")
        return None, text if delta else "turn me", None

    def _mode_turn(self, knob, mode, delta):
        frac, text, title = self._mode_value(mode, delta)
        if mode == "pages":
            return
        name, icon = self._mode_meta(mode)
        self.hud(icon, title or name, frac, text)

    def _mode_next(self, knob):
        kn = self.cfg["knobs"][str(knob)]
        modes = kn.get("modes") or []
        if not modes:
            return
        kn["mode"] = (kn.get("mode", 0) + 1) % len(modes)
        mode = modes[kn["mode"]]
        name, icon = self._mode_meta(mode)
        frac, text, title = self._mode_value(mode, 0)
        self.hud(icon, title or name, frac, text)
        self.emit({"t": "mode", "idx": knob, "mode": mode, "name": name})
        self._stats_dirty = True

    def _mode_alt(self, knob):
        kn = self.cfg["knobs"][str(knob)]
        modes = kn.get("modes") or []
        mode = modes[kn.get("mode", 0) % len(modes)] if modes else ""
        name, icon = self._mode_meta(mode)
        if mode == "volume":
            m = self.audio.master_mute_toggle()
            if m is None:
                actions.run({"type": "media", "value": "mute"})
            self.hud("muted_speaker" if m else icon, name, None, "muted" if m else "sound on")
        elif mode in ("app_media", "app_focus") or mode.startswith("app:"):
            exe = self.np.app_exe() if mode == "app_media" else (context.foreground()[0] if mode == "app_focus" else mode[4:])
            self.audio.app(exe, toggle_mute=True)
            self.hud("muted_speaker", name, None, "mute toggled")
        elif mode in ("scrub", "tracks"):
            self.run_action({"type": "np", "value": "toggle"})
            self.hud(icon, name, None, "play / pause")
        elif mode == "zoom":
            actions.run({"type": "hotkey", "value": "ctrl+0"})
            self.hud(icon, name, None, "reset")
        elif mode == "pages":
            self._page_action("1")
        elif mode == "brightness":
            v = self.bright.change(100)
            self.hud(icon, name, 1.0 if v else None, "100%" if v else "n/a")

    def hud(self, icon, title, frac, text):
        self._hud_state = (icon, title, frac, text)
        self._hud_until = time.time() + HUD_S
        self._hud_ev.set()
        self.emit({"t": "hud", "title": title, "frac": frac, "text": text, "icon": icons.p3d(icon)})

    def _hud_loop(self):
        last = None
        while True:
            self._hud_ev.wait()
            self._hud_ev.clear()
            st = self._hud_state
            if st == last or not self.deck or self.game or self._busy:
                continue
            last = st
            icon, title, frac, text = st
            try:
                tiles = render.hud_tiles(render.load_icon(icons.p3d(icon)), title, frac, text, self.accent())
                for j, t in enumerate(tiles):
                    self.deck.set_key_image(3 + j, t)
                self._hud_on = True
            except Exception as e:
                print("HUD error:", e)
            time.sleep(0.06)

    # ---------------- the animation / live loop ----------------
    def _interval(self, p, i, k):
        if i in self._overlay:
            return 0.1
        if self.party:
            return 0.16
        live = k.get("live")
        if live == "nowplaying":
            return 0.16 if self.np.info.get("playing") else 1.0
        if live == "timer":
            return 0.33 if (self.timer["running"] or self.timer["done"]) else 1.0
        if live == "mic":
            return 0.5
        if live:
            return 1.0
        if k.get("icon") and render.gif_frames(k["icon"]):
            return 0.1
        if k.get("badge"):
            return 2.0
        return None

    def _anim_loop(self):
        while True:
            time.sleep(0.05)
            try:
                self._timer_tick()
                now = time.time()
                if self.game or self._busy:
                    continue
                p = self.page_index
                if self._hud_on and now > self._hud_until:
                    self._hud_on = False
                    for i in (3, 4, 5):
                        self._due[i] = 0
                for i, ov in list(self._overlay.items()):
                    if now >= ov["until"]:
                        self._overlay.pop(i, None)
                        self._due[i] = 0
                keys = self.cfg["pages"][p]["keys"]
                studio, live_kinds = {}, []
                for i in range(6):
                    k = keys[str(i)]
                    if k.get("live"):
                        live_kinds.append(k["live"])
                    iv = self._interval(p, i, k)
                    due = self._due.get(i)
                    if iv is None and due is None:
                        continue
                    if due is not None and now < due:
                        continue
                    self._due[i] = now + iv if iv is not None else None
                    if iv is None:
                        self._due.pop(i, None)
                    if self._hud_on and i >= 3:
                        continue
                    if self.deck:
                        self.deck.set_key_image(i, self.key_image(p, i, 60, device=True, t=now))
                    if self._listeners and now >= self._studio_due.get(i, 0):
                        studio[i] = data_url(self.key_image(p, i, 192, t=now))
                        self._studio_due[i] = now + 0.22
                if studio:
                    self.emit({"t": "live", "page": p, "previews": studio, "vitals": self.summary(live_kinds)})
            except Exception as e:
                print("Anim error:", e)
                time.sleep(0.5)

    # ---------------- smart pages ----------------
    def _smart_loop(self):
        while True:
            time.sleep(0.7)
            try:
                sm = self.cfg.get("smart", {})
                if not sm.get("enabled", True) or self.game:
                    continue
                exe, path, title = context.foreground()
                if not exe or (title.startswith("AKP03 Deck") and exe in ("msedge.exe", "chrome.exe")):
                    continue
                if exe == self._last_fg:
                    continue
                self._last_fg = exe
                target = None
                for idx, pg in enumerate(self.cfg["pages"]):
                    if exe in [a.lower() for a in pg.get("apps", [])] or (pg.get("games") and context.is_game(exe, path)):
                        target = idx
                        break
                cur = self.page_index
                if target is not None:
                    if target != cur:
                        if self._auto is None:
                            self._auto = {"return": cur}
                        self.goto_page(target, auto=True)
                        self.emit({"t": "auto", "page": target, "app": exe})
                elif self._auto and sm.get("go_back", True):
                    ret = self._auto["return"]
                    self._auto = None
                    if ret != cur and ret < len(self.cfg["pages"]):
                        self.goto_page(ret, auto=True)
                        self.emit({"t": "auto", "page": ret, "app": "", "back": True})
            except Exception as e:
                print("Smart pages error:", e)

    # ---------------- stats + icons ----------------
    def _stats_loop(self):
        while True:
            time.sleep(15)
            if self._stats_dirty:
                self._stats_dirty = False
                try:
                    self.save()
                except Exception:
                    pass

    def _auto_icons(self):
        """Swap letter tiles for the real app icon when the app is installed."""
        time.sleep(3)
        import appicons
        changed = False
        for p in self.cfg["pages"]:
            for k in p["keys"].values():
                if k.get("icon_auto") and k.get("exe"):
                    k["icon_auto"] = False
                    try:
                        k["icon"] = icons.rel(appicons.extract(k["exe"]))
                        changed = True
                    except Exception:
                        pass
        if changed:
            self.save()
            self.push_page()
            self.emit({"t": "refresh"})

    # ---------------- connection ----------------
    def reconnect(self, reason="manual"):
        d = self.deck
        self.deck = None
        self.game = None
        if d:
            log.warning("Reconnecting deck (%s)", reason)
            try:
                d.close(clear=False)
            except Exception:
                pass
        self.health.update(state="reconnecting", last_error=reason)
        self.health["reconnects"] += 1
        self.emit({"t": "status", "connected": False, "state": "reconnecting"})

    def _connect_loop(self):
        backoff = 1.0
        last_tick = time.time()
        while True:
            now = time.time()
            woke = now - last_tick > 15  # the PC was asleep: USB devices often need a fresh start
            last_tick = now
            d = self.deck
            if d is not None:
                if woke:
                    self.reconnect("PC woke from sleep")
                elif d.stalled():
                    self.reconnect("stalled")
                time.sleep(0.5)
                continue
            if True:
                try:
                    d = akp03.Deck.open_first()
                    d.on_key = self._on_key
                    d.on_knob_turn = self._on_knob_turn
                    d.on_knob_press = self._on_knob_press
                    d.on_disconnect = self._lost
                    self.deck = d
                    d.set_brightness(self.cfg.get("brightness", 80))
                    self.push_page(splash=True, credits=True)
                    d.start()
                    self._due.clear()
                    self.health.update(state="connected", since=time.time())
                    log.info("Deck connected %s", d.id_string)
                    self.emit({"t": "status", "connected": True, "state": "connected"})
                    backoff = 1.0
                except Exception as e:
                    self.deck = None
                    if self.health["state"] != "searching":
                        log.info("Deck not available: %s", e)
                    self.health["state"] = "searching"
                    time.sleep(backoff)
                    backoff = min(5.0, backoff * 1.5)

    def _lost(self):
        if self.deck is None:
            return
        self.deck = None
        self.game = None
        self.health.update(state="reconnecting", last_error="unplugged or USB error")
        self.health["reconnects"] += 1
        log.warning("Deck lost, will reconnect")
        self.emit({"t": "status", "connected": False, "state": "reconnecting"})

    def close(self):
        try:
            self.save()
        except Exception:
            pass
        if self.deck:
            self.deck.close()
