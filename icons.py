"""The icon pack: 3D icons (Fluent Emoji) + brand tiles. Missing 3D icons download on demand."""
from __future__ import annotations

import json
import os
import threading
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.join(HERE, "pack")

_man = None
_remote: dict[str, str] = {}
_pending: set[str] = set()
_lock = threading.Lock()


def manifest() -> dict:
    global _man
    if _man is None:
        try:
            with open(os.path.join(PACK, "manifest.json"), encoding="utf-8") as f:
                _man = json.load(f)
        except Exception:
            _man = {"emoji": {}, "icons": [], "brands": []}
        for it in _man.get("icons", []):
            if it.get("r"):
                _remote[it["f"]] = it["r"]
    return _man


def resolve(path: str) -> str:
    """Icons in the config are stored relative to the app folder when possible."""
    if not path:
        return ""
    return path if os.path.isabs(path) else os.path.join(HERE, path)


def rel(path: str) -> str:
    try:
        r = os.path.relpath(path, HERE)
        return r.replace("\\", "/") if not r.startswith("..") else path
    except ValueError:
        return path


def fetch(f: str, wait: bool = False) -> str | None:
    """Make sure pack/<f> exists, downloading it if needed. Returns the full path or None."""
    manifest()
    dest = os.path.join(PACK, f)
    if os.path.exists(dest):
        return dest
    url = _remote.get(f)
    if not url:
        return None

    def work():
        try:
            from PIL import Image
            import io
            with urllib.request.urlopen(url, timeout=15) as r:
                img = Image.open(io.BytesIO(r.read())).convert("RGBA")
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            img.resize((160, 160), Image.LANCZOS).save(dest, optimize=True)
        except Exception as e:
            print("Icon download failed:", e)
        finally:
            with _lock:
                _pending.discard(f)

    with _lock:
        if f in _pending and not wait:
            return None
        _pending.add(f)
    if wait:
        work()
        return dest if os.path.exists(dest) else None
    threading.Thread(target=work, daemon=True).start()
    return None


def emoji_file(glyph: str) -> str | None:
    """3D version of an emoji, if we have (or can get) it."""
    f = manifest()["emoji"].get(glyph.replace("\ufe0f", "").strip())
    return fetch(f) if f else None


def p3d(name: str) -> str:
    return f"pack/3d/{name}.png"


def brand(name: str) -> str:
    return f"pack/brands/{name}.png"
