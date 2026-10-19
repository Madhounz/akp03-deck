"""Windows integrations: now playing, volumes, mic, screen brightness, Outlook unread.

Every part is optional. If a package is missing, that feature quietly turns off.
"""
from __future__ import annotations

import asyncio
import io
import threading
import time

try:
    import psutil
except ImportError:
    psutil = None


# ---------------- audio (pycaw) ----------------

def _com():
    try:
        import comtypes
        comtypes.CoInitialize()
    except Exception:
        pass


def _endpoint(mic=False):
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    dev = AudioUtilities.GetMicrophone() if mic else AudioUtilities.GetSpeakers()
    ev = getattr(dev, "EndpointVolume", None)
    if ev is not None:
        return ev
    from ctypes import POINTER, cast
    from comtypes import CLSCTX_ALL
    iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(iface, POINTER(IAudioEndpointVolume))


class Audio:
    def __init__(self):
        try:
            import pycaw  # noqa
            self.ok = True
        except Exception:
            self.ok = False
        self._mic_cache = (0.0, None)

    def master(self, delta: float = 0.0):
        """Change master volume by delta (0..1). Returns new level or None."""
        if not self.ok:
            return None
        try:
            _com()
            ev = _endpoint()
            v = max(0.0, min(1.0, ev.GetMasterVolumeLevelScalar() + delta))
            if delta:
                ev.SetMasterVolumeLevelScalar(v, None)
                if v > 0 and ev.GetMute():
                    ev.SetMute(0, None)
            return v
        except Exception as e:
            print("Volume error:", e)
            return None

    def set_master(self, v: float):
        cur = self.master(0)
        return None if cur is None else self.master(max(0.0, min(1.0, v)) - cur)

    def master_muted(self):
        if not self.ok:
            return None
        try:
            _com()
            return bool(_endpoint().GetMute())
        except Exception:
            return None

    def master_mute_toggle(self):
        try:
            _com()
            ev = _endpoint()
            ev.SetMute(0 if ev.GetMute() else 1, None)
            return bool(ev.GetMute())
        except Exception:
            return None

    def mic_muted(self):
        if not self.ok:
            return None
        t, v = self._mic_cache
        if time.time() - t < 0.8:
            return v
        try:
            _com()
            v = bool(_endpoint(mic=True).GetMute())
        except Exception:
            v = None
        self._mic_cache = (time.time(), v)
        return v

    def mic_toggle(self):
        try:
            _com()
            ev = _endpoint(mic=True)
            ev.SetMute(0 if ev.GetMute() else 1, None)
            self._mic_cache = (0.0, None)
            return bool(ev.GetMute())
        except Exception as e:
            print("Mic error:", e)
            return None

    def _sessions(self, match: str):
        from pycaw.pycaw import AudioUtilities
        match = (match or "").lower().replace(".exe", "")
        out = []
        for s in AudioUtilities.GetAllSessions():
            try:
                name = s.Process.name().lower() if s.Process else ""
            except Exception:
                name = ""
            if match and match in name:
                out.append((name, s.SimpleAudioVolume))
        return out

    def app(self, match: str, delta: float = 0.0, toggle_mute=False):
        """Volume of one app (by exe name). Returns (level, app name) or (None, None)."""
        if not self.ok or not match:
            return None, None
        try:
            _com()
            ss = self._sessions(match)
            if not ss:
                return None, None
            name, vol = ss[0]
            v = max(0.0, min(1.0, vol.GetMasterVolume() + delta))
            for _, sv in ss:
                if toggle_mute:
                    sv.SetMute(0 if sv.GetMute() else 1, None)
                elif delta:
                    sv.SetMasterVolume(v, None)
            return v, name.replace(".exe", "")
        except Exception as e:
            print("App volume error:", e)
            return None, None

    def apps(self):
        """Apps that are playing sound right now."""
        if not self.ok:
            return []
        try:
            _com()
            from pycaw.pycaw import AudioUtilities
            return sorted({s.Process.name() for s in AudioUtilities.GetAllSessions() if s.Process})
        except Exception:
            return []


# ---------------- screen brightness ----------------

class Brightness:
    def __init__(self):
        try:
            import screen_brightness_control as sbc
            self.sbc = sbc
        except Exception:
            self.sbc = None
        self._v = None
        self._target = None
        self._ev = threading.Event()
        if self.sbc:
            threading.Thread(target=self._worker, daemon=True).start()

    def change(self, delta: int):
        if not self.sbc:
            return None
        if self._v is None:
            try:
                self._v = int(self.sbc.get_brightness(display=0)[0])
            except Exception:
                self._v = 50
        self._v = max(0, min(100, self._v + delta))
        self._target = self._v
        self._ev.set()
        return self._v

    def set(self, v: int):
        if not self.sbc:
            return None
        self._v = max(0, min(100, int(v)))
        self._target = self._v
        self._ev.set()
        return self._v

    def current(self):
        """Read the real value once (slow on some monitors), then remember it."""
        if not self.sbc:
            return None
        if self._v is None:
            try:
                self._v = int(self.sbc.get_brightness(display=0)[0])
            except Exception:
                return None
        return self._v

    def _worker(self):  # monitors are slow, so only send the latest value
        while True:
            self._ev.wait()
            self._ev.clear()
            v = self._target
            try:
                self.sbc.set_brightness(v, display=0)
            except Exception:
                pass


# ---------------- now playing (Windows media session) ----------------

class NowPlaying:
    """Reads what Windows says is playing (Spotify, browsers, Media Player...)."""

    def __init__(self):
        self.ok = False
        self.info = {"title": "", "artist": "", "playing": False, "art": None, "app": ""}
        self._loop = None
        self._session = None
        self.wanted = lambda: True  # core replaces this
        try:
            from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager  # noqa
            self.ok = True
        except Exception:
            try:
                from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionManager  # noqa
                self.ok = True
            except Exception:
                self.ok = False
        if self.ok:
            threading.Thread(target=self._run, daemon=True).start()

    @staticmethod
    def _mods():
        try:
            from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as M
            from winrt.windows.storage.streams import Buffer, InputStreamOptions, DataReader
        except Exception:
            from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as M
            from winsdk.windows.storage.streams import Buffer, InputStreamOptions, DataReader
        return M, Buffer, InputStreamOptions, DataReader

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._poll())

    async def _poll(self):
        M, Buffer, Opts, DataReader = self._mods()
        mgr = None
        last_key = None
        while True:
            try:
                if mgr is None:
                    mgr = await M.request_async()
                s = mgr.get_current_session()
                self._session = s
                if not s:
                    self.info = {"title": "", "artist": "", "playing": False, "art": None, "app": ""}
                else:
                    props = await s.try_get_media_properties_async()
                    status = s.get_playback_info().playback_status
                    playing = int(status) == 4
                    key = (props.title, props.artist)
                    art = self.info.get("art")
                    if key != last_key:
                        art = None
                        try:
                            if props.thumbnail:
                                stream = await props.thumbnail.open_read_async()
                                buf = Buffer(stream.size)
                                await stream.read_async(buf, buf.capacity, Opts.READ_AHEAD)
                                try:
                                    data = bytes(buf)
                                except Exception:
                                    r = DataReader.from_buffer(buf)
                                    arr = bytearray(buf.length)
                                    r.read_bytes(arr)
                                    data = bytes(arr)
                                from PIL import Image
                                art = Image.open(io.BytesIO(data)).convert("RGB")
                                art = _crop_letterbox(art)
                        except Exception as e:
                            print("Album art error:", e)
                        last_key = key
                    self.info = {"title": props.title or "", "artist": props.artist or "", "playing": playing,
                                 "art": art, "app": s.source_app_user_model_id or ""}
            except Exception as e:
                print("Now playing error:", e)
                mgr = None
                await asyncio.sleep(3)
            await asyncio.sleep(1.0 if self.wanted() else 4.0)

    def _call(self, name):
        s = self._session
        if not (self.ok and s and self._loop):
            return False
        async def go():
            await getattr(s, name)()
        try:
            asyncio.run_coroutine_threadsafe(go(), self._loop)
            return True
        except Exception:
            return False

    def toggle(self):
        return self._call("try_toggle_play_pause_async")

    def next(self):
        return self._call("try_skip_next_async")

    def previous(self):
        return self._call("try_skip_previous_async")

    def app_exe(self) -> str:
        """Best guess of the playing app's process name, for per-app volume."""
        a = (self.info.get("app") or "").split("!")[0].lower()
        if a.endswith(".exe"):
            return a
        for name in ("spotify", "chrome", "msedge", "firefox", "brave", "opera", "vlc", "music", "zune", "itunes"):
            if name in a:
                return {"zune": "music", "music": "music"}.get(name, name)
        return a.split(".")[-1] if a else ""


def _crop_letterbox(img):
    """Some apps send art with black bars. Trim them."""
    try:
        from PIL import ImageChops, Image
        bg = Image.new(img.mode, img.size, img.getpixel((0, 0)))
        box = ImageChops.difference(img, bg).convert("L").point(lambda v: 255 if v > 18 else 0).getbbox()
        if box and (box[2] - box[0]) > img.width * 0.4:
            return img.crop(box)
    except Exception:
        pass
    return img


# ---------------- Outlook unread count ----------------

class Outlook:
    def __init__(self):
        self.count = 0
        self.ok = False
        self.wanted = False
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            if self.wanted:
                try:
                    import pythoncom
                    import win32com.client
                    pythoncom.CoInitialize()
                    if psutil and not any(p.info["name"] and p.info["name"].lower() == "outlook.exe"
                                          for p in psutil.process_iter(["name"])):
                        raise RuntimeError("Outlook is not running")
                    ns = win32com.client.GetActiveObject("Outlook.Application").GetNamespace("MAPI")
                    self.count = int(ns.GetDefaultFolder(6).UnReadItemCount)
                    self.ok = True
                except Exception:
                    self.ok = False
            time.sleep(20)
