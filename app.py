"""AKP03 Deck: runs in the tray, serves the studio UI, drives the Ajazz AKP03E."""
from __future__ import annotations

import json
import logging
import os
import queue
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import actions
import akp03
import appicons
import ai
import context
import icons
import library
import monitor
from core import Core, KNOB_MODES
from render import app_icon

HERE = os.path.dirname(os.path.abspath(__file__))
UI_FILE = os.path.join(HERE, "ui", "index.html")
ICON_DIR = os.path.join(HERE, "icons")
APP_NAME = "AKP03Deck"
PORT = 47613
URL = f"http://127.0.0.1:{PORT}/"
TOKEN = secrets.token_hex(16)  # stops random websites from talking to this app

core: Core | None = None


# ---------------- start with Windows ----------------
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def startup_enabled() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except Exception:
        return False


def set_startup(on: bool):
    import winreg
    exe = sys.executable
    if exe.lower().endswith("python.exe") and os.path.exists(exe[:-10] + "pythonw.exe"):
        exe = exe[:-10] + "pythonw.exe"
    # start through the launcher, which also restarts the app if it ever crashes or hangs
    cmd = f'"{exe}" "{os.path.join(HERE, "launcher.pyw")}" --boot'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except FileNotFoundError:
                pass


# ---------------- helpers ----------------
_dialog_lock = threading.Lock()


def ask_file(title: str, types) -> str:
    """Native Windows file picker (used for picking apps)."""
    with _dialog_lock:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            return filedialog.askopenfilename(title=title, filetypes=types, parent=root) or ""
        finally:
            root.destroy()


def open_ui():
    """Open the studio as a clean app window (Edge app mode), or the normal browser."""
    candidates = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]
    for exe in candidates:
        if os.path.isfile(exe):
            subprocess.Popen([exe, f"--app={URL}", "--window-size=1500,920"])
            return
    webbrowser.open(URL)


# ---------------- API (called by the UI) ----------------
def _page(p):
    return core.cfg["pages"][int(p)]


class Api:
    @staticmethod
    def state(_):
        return {
            "cfg": core.cfg,
            "previews": {core.page_index: core.previews(core.page_index)},
            "connected": core.deck is not None,
            "startup": startup_enabled(),
            "library": library.LIBRARY,
            "emojis": library.EMOJIS,
            "accents": library.ACCENTS,
            "types": actions.ACTION_TYPES,
            "hints": actions.HINTS,
            "suggestions": actions.SUGGESTIONS,
            "metrics": core.metrics_list(),
            "monitor": core.monitor_status(),
            "credits": {"author": library.AUTHOR, "studio": library.STUDIO, "version": library.VERSION},
            "knob_modes": {k: v[0] for k, v in KNOB_MODES.items()},
            "ai_modes": {k: v[0] for k, v in ai.MODES.items()},
            "ai": {"has_key": bool(core.secret.get("api_key")), "model": core.secret.get("model") or ai.DEFAULT_MODEL},
            "game": core.game.name if core.game else "",
        }

    @staticmethod
    def health(_):
        d = core.deck
        return {**core.health, "connected": d is not None, "id": d.id_string if d else "",
                "io": dict(d.stats) if d else {}, "memory_mb": _memory_mb()}

    @staticmethod
    def reconnect(_):
        core.reconnect("manual")
        return {"ok": True}

    @staticmethod
    def export_config(_):
        return {"cfg": core.cfg}

    @staticmethod
    def import_config(b):
        cfg = b.get("cfg")
        if not isinstance(cfg, dict) or not isinstance(cfg.get("pages"), list) or not cfg["pages"]:
            return {"error": "That file is not an AKP03 Deck setup."}
        import shutil
        if os.path.exists(os.path.join(HERE, "config.json")):
            shutil.copy2(os.path.join(HERE, "config.json"), os.path.join(HERE, "config.before-import.json"))
        with core.lock:
            core.cfg = library.upgrade_v5(cfg) if cfg.get("version", 5) < 5 else cfg
            core.cfg.setdefault("stats", {"presses": {}, "best": {}})
            core.cfg["current_page"] = 0
            core.save()
        core.cfg = core._load()
        core.push_page(splash=True)
        core.emit({"t": "reload"})
        return {"ok": True}

    @staticmethod
    def monitor(_):
        return core.monitor_status()

    @staticmethod
    def set_ai(b):
        if "key" in b:
            core.secret["api_key"] = str(b["key"]).strip()
        if "model" in b:
            core.secret["model"] = str(b["model"]).strip()
        core.save_secret()
        return {"has_key": bool(core.secret.get("api_key")), "model": core.secret.get("model") or ai.DEFAULT_MODEL}

    @staticmethod
    def test_ai(_):
        try:
            out = ai.ask(core.secret.get("api_key", ""), core.secret.get("model", ""), "custom", "ping",
                         "Reply with exactly: Connected and ready.")
            return {"ok": True, "text": out}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @staticmethod
    def running_apps(_):
        return {"apps": context.running_apps(), "audio": core.audio.apps()}

    @staticmethod
    def stats(_):
        return {"stats": core.cfg.get("stats", {})}

    @staticmethod
    def reset_stats(_):
        core.cfg["stats"] = {"presses": {}, "best": core.cfg.get("stats", {}).get("best", {})}
        core.save()
        return {"stats": core.cfg["stats"]}

    @staticmethod
    def fetch_icon(b):
        f = str(b.get("f", ""))
        p = icons.fetch(f, wait=True)
        return {"path": "pack/" + f} if p else {"error": "Could not download that icon. Check your internet."}

    @staticmethod
    def start_game(b):
        core.start_game(str(b.get("name", "")))
        return {"ok": True}

    @staticmethod
    def stop_game(_):
        core.stop_game()
        return {"ok": True}

    @staticmethod
    def open_url(b):
        u = str(b.get("url", ""))
        if u.startswith("https://"):
            webbrowser.open(u)
        return {"ok": True}

    @staticmethod
    def previews(b):
        return {"page": b["page"], "previews": core.previews(int(b["page"]))}

    @staticmethod
    def update_key(b):
        p, i = int(b["page"]), int(b["idx"])
        with core.lock:
            _page(p)["keys"][str(i)].update(b["patch"])
            core.save()
        core.push_key(p, i)
        return {"page": p, "idx": i, "preview": _one_preview(p, i)}

    @staticmethod
    def update_control(b):
        group = "buttons" if b["kind"] == "button" else "knobs"
        with core.lock:
            core.cfg[group][str(b["idx"])].update(b["patch"])
            core.save()
        return {"ok": True}

    @staticmethod
    def update_page(b):
        p = int(b["page"])
        with core.lock:
            _page(p).update(b["patch"])
            core.save()
        if p == core.page_index:
            core.push_page(splash=False)
        return {"page": p, "previews": core.previews(p), "cfg": core.cfg}

    @staticmethod
    def add_page(b):
        with core.lock:
            core.cfg["pages"].append(library.blank_page(len(core.cfg["pages"]) + 1))
            core.save()
        core.goto_page(len(core.cfg["pages"]) - 1)
        return {"cfg": core.cfg}

    @staticmethod
    def duplicate_page(b):
        import copy
        p = int(b["page"])
        with core.lock:
            dup = copy.deepcopy(_page(p))
            dup["name"] = dup.get("name", "Page") + " copy"
            core.cfg["pages"].insert(p + 1, dup)
            core.save()
        core.goto_page(p + 1)
        return {"cfg": core.cfg}

    @staticmethod
    def delete_page(b):
        p = int(b["page"])
        with core.lock:
            if len(core.cfg["pages"]) > 1:
                core.cfg["pages"].pop(p)
            core.cfg["current_page"] = min(core.page_index, len(core.cfg["pages"]) - 1)
            core.save()
        core.goto_page(min(p, len(core.cfg["pages"]) - 1), splash=False)
        core.push_page(splash=True)
        return {"cfg": core.cfg}

    @staticmethod
    def move_page(b):
        p, d = int(b["page"]), int(b["dir"])
        q = p + d
        with core.lock:
            pages = core.cfg["pages"]
            if 0 <= q < len(pages):
                pages[p], pages[q] = pages[q], pages[p]
                core.cfg["current_page"] = q
                core.save()
        core.emit({"t": "page", "page": core.page_index})
        return {"cfg": core.cfg}

    @staticmethod
    def goto_page(b):
        core.goto_page(int(b["page"]))
        return {"page": core.page_index}

    @staticmethod
    def settings(b):
        patch = b.get("patch", {})
        if "brightness" in patch:
            core.set_brightness(patch["brightness"])
        if "splash" in patch:
            core.cfg["splash"] = bool(patch["splash"])
        if "startup" in patch:
            set_startup(bool(patch["startup"]))
        if "smart" in patch:
            core.cfg.setdefault("smart", {}).update(patch["smart"])
        if "timer_minutes" in patch:
            core.cfg["timer_minutes"] = max(1, min(240, int(patch["timer_minutes"])))
            core._timer_action("reset")
        core.save()
        return {"startup": startup_enabled(), "cfg": core.cfg}

    @staticmethod
    def test_action(b):
        core.run_action(b.get("action"))
        return {"ok": True}

    @staticmethod
    def browse_app(_):
        p = ask_file("Choose an app or file", [("Apps and files", "*.exe *.lnk *.bat *.cmd *.*")])
        return {"path": p.replace("/", "\\") if p else ""}

    @staticmethod
    def app_icon(b):
        try:
            return {"path": icons.rel(appicons.extract(b.get("value", "")))}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def open_folder(_):
        os.startfile(HERE)
        return {"ok": True}

    @staticmethod
    def reset(_):
        core.reset()
        return {"ok": True}


def _one_preview(p, i):
    from core import data_url
    return data_url(core.key_image(p, i, 192))


def _memory_mb():
    try:
        import psutil
        return round(psutil.Process().memory_info().rss / 1024 ** 2)
    except Exception:
        return None


# ---------------- tiny web server ----------------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _host_ok(self) -> bool:
        return self.headers.get("Host", "").split(":")[0] in ("127.0.0.1", "localhost")

    def _send(self, code, body: bytes, ctype="application/json", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, b"forbidden", "text/plain")
        u = urlparse(self.path)
        if u.path == "/":
            with open(UI_FILE, encoding="utf-8") as f:
                html = f.read().replace("__TOKEN__", TOKEN)
            return self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
        if u.path == "/alive":
            return self._send(200, b"ok", "text/plain")
        if u.path == "/poke":
            if flyout is not None:
                flyout.root.after(0, flyout.show)
            return self._send(200, b"ok", "text/plain")
        if u.path == "/ui.js":
            with open(os.path.join(HERE, "ui", "ui.js"), encoding="utf-8") as f:
                js = f.read().replace("__TOKEN__", TOKEN)
            return self._send(200, js.encode("utf-8"), "text/javascript; charset=utf-8")
        if u.path.startswith("/pack/") or u.path.startswith("/icons/"):
            from urllib.parse import unquote
            base = os.path.join(HERE, "pack" if u.path.startswith("/pack/") else "icons")
            full = os.path.normpath(os.path.join(HERE, unquote(u.path.lstrip("/"))))
            if not full.startswith(base) or not os.path.isfile(full):
                return self._send(404, b"not found", "text/plain")
            ext = os.path.splitext(full)[1].lower()
            ctype = {".png": "image/png", ".json": "application/json", ".gif": "image/gif", ".jpg": "image/jpeg",
                     ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(ext, "application/octet-stream")
            with open(full, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "max-age=86400")
            self.end_headers()
            self.wfile.write(data)
            return
        if u.path == "/favicon.png":
            import io
            buf = io.BytesIO()
            app_icon(128).save(buf, "PNG")
            return self._send(200, buf.getvalue(), "image/png")
        if u.path == "/events":
            if parse_qs(u.query).get("token", [""])[0] != TOKEN:
                return self._send(403, b"forbidden", "text/plain")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            q = core.subscribe()
            try:
                self.wfile.write(b"retry: 1500\n\n")
                self.wfile.flush()
                while True:
                    try:
                        ev = q.get(timeout=15)
                        self.wfile.write(b"data: " + json.dumps(ev).encode() + b"\n\n")
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
            except Exception:
                pass
            finally:
                core.unsubscribe(q)
            return
        self._send(404, b"not found", "text/plain")

    def do_POST(self):
        if not self._host_ok() or self.headers.get("X-Deck-Token") != TOKEN:
            return self._send(403, b'{"error":"forbidden"}')
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n) if n else b""
        if u.path == "/upload":
            name = re.sub(r"[^\w.-]", "_", self.headers.get("X-Name", "image.png"))[-80:]
            os.makedirs(ICON_DIR, exist_ok=True)
            base, ext = os.path.splitext(name)
            dest = os.path.join(ICON_DIR, f"{base}_{int(time.time())}{ext or '.png'}")
            with open(dest, "wb") as f:
                f.write(raw)
            return self._send(200, json.dumps({"path": icons.rel(dest)}).encode())
        if u.path.startswith("/api/"):
            fn = getattr(Api, u.path[5:], None)
            if not fn:
                return self._send(404, b'{"error":"no such api"}')
            try:
                body = json.loads(raw or b"{}")
                res = fn(body)
                return self._send(200, json.dumps(res, ensure_ascii=False).encode("utf-8"))
            except Exception as e:
                return self._send(500, json.dumps({"error": str(e)}).encode())
        self._send(404, b'{"error":"not found"}')


# ---------------- main ----------------
def setup_logging():
    """Small rolling log file (akp03.log) so freezes can be traced. Also catches crashes in threads."""
    import logging
    from logging.handlers import RotatingFileHandler
    h = RotatingFileHandler(os.path.join(HERE, "akp03.log"), maxBytes=256_000, backupCount=1, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(h)

    class ToLog:
        def __init__(self, level):
            self.level = level

        def write(self, msg):
            msg = msg.strip()
            if msg:
                logging.log(self.level, msg)

        def flush(self):
            pass

    if sys.stdout is None or "pythonw" in (sys.executable or "").lower():
        sys.stdout, sys.stderr = ToLog(logging.INFO), ToLog(logging.ERROR)
    threading.excepthook = lambda a: logging.error("Thread crash", exc_info=(a.exc_type, a.exc_value, a.exc_traceback))
    logging.info("AKP03 Deck %s starting", library.VERSION)


flyout = None


def main():
    global core, flyout
    if "--list" in sys.argv:
        print("\n".join(akp03.list_all_hid()))
        return

    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        if "--minimized" in sys.argv:
            return  # started by Windows or the launcher while already running: stay quiet
        # already running: ask it to pop up its panel by the clock
        try:
            import urllib.request
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/poke", timeout=2).read()
        except Exception:
            open_ui()
        return
    server.daemon_threads = True
    setup_logging()
    first_run = not os.path.exists(os.path.join(HERE, "config.json"))

    core = Core()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    if os.name == "nt" and not core.cfg.get("startup_set"):
        # Turn "start with Windows" on once by default, so the deck never sits frozen after a restart.
        try:
            set_startup(True)
            core.cfg["startup_set"] = True
            core.save()
            logging.info("Start with Windows turned on")
        except Exception as e:
            logging.warning("Could not turn on start with Windows: %s", e)
    elif startup_enabled():
        try:
            set_startup(True)  # refresh the entry so it always points at this folder and the launcher
        except Exception:
            pass

    from flyout import Flyout

    def quit_app(*_):
        try:
            if tray:
                tray.stop()
        except Exception:
            pass
        core.close()
        os._exit(0)

    flyout = Flyout(core, open_ui, quit_app)
    if os.name == "nt":
        flyout.startup = (startup_enabled, set_startup)
    ui = flyout.root

    tray = None
    try:
        import pystray
        tray = pystray.Icon(APP_NAME, app_icon(64), "AKP03 Deck", pystray.Menu(
            pystray.MenuItem("Quick panel", lambda *_: ui.after(0, flyout.toggle), default=True),
            pystray.MenuItem("Open studio", lambda *_: open_ui()),
            pystray.MenuItem("Next page", lambda *_: core.run_action({"type": "page", "value": "next"})),
            pystray.MenuItem("Reconnect deck", lambda *_: core.reconnect("manual")),
            pystray.MenuItem("Open log file", lambda *_: os.startfile(os.path.join(HERE, "akp03.log"))),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda *_: quit_app()),
        ))
        tray.run_detached()
    except Exception as e:
        print("Tray not available:", e)

    if first_run:
        threading.Timer(0.6, open_ui).start()
    elif "--minimized" not in sys.argv:
        ui.after(700, flyout.show)
    flyout.run()


if __name__ == "__main__":
    main()
