"""Grab a real, high resolution icon from a Windows app (exe or app link)."""
from __future__ import annotations

import io
import os
import re
import shutil

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ICON_DIR = os.path.join(HERE, "icons")


def _reg(root, path, name=""):
    try:
        import winreg
        with winreg.OpenKey(root, path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except Exception:
        return None


def _first_path(cmd: str) -> str | None:
    """Pull the exe path out of a registry command line like "C:\\x\\app.exe" --url %1."""
    if not cmd:
        return None
    cmd = os.path.expandvars(cmd.strip())
    m = re.match(r'"([^"]+)"', cmd) or re.match(r"(\S+\.exe)", cmd, re.I)
    return m.group(1) if m else None


def resolve(value: str) -> str | None:
    """Turn 'excel.exe', 'spotify:' or a full path into an exe/icon file path."""
    if not value:
        return None
    v = os.path.expandvars(value.strip().strip('"'))
    if os.path.isfile(v):
        return v
    try:
        import winreg
    except ImportError:
        return shutil.which(v)
    # app links like spotify: or zoommtg:
    if re.fullmatch(r"[a-zA-Z][\w.+-]*:", v):
        scheme = v[:-1]
        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_CLASSES_ROOT):
            p = _first_path(_reg(root, rf"Software\Classes\{scheme}\shell\open\command" if root == winreg.HKEY_CURRENT_USER
                                 else rf"{scheme}\shell\open\command"))
            if p and os.path.isfile(p):
                return p
        return None
    name = v if v.lower().endswith(".exe") else v + ".exe"
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for base in (r"Software\Microsoft\Windows\CurrentVersion\App Paths",
                     r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths"):
            p = _reg(root, rf"{base}\{name}")
            if p:
                p = os.path.expandvars(p.strip('"'))
                if os.path.isfile(p):
                    return p
    return shutil.which(name)


def extract(value: str) -> str:
    """Save the app's biggest icon as a PNG in icons/ and return its path."""
    path = resolve(value)
    if not path:
        raise RuntimeError("Could not find that app on this PC")
    os.makedirs(ICON_DIR, exist_ok=True)
    base = re.sub(r"[^\w.-]", "_", os.path.splitext(os.path.basename(path))[0]) or "app"
    out = os.path.join(ICON_DIR, f"app_{base}.png")
    ext = os.path.splitext(path)[1].lower()
    if ext in (".png", ".jpg", ".jpeg", ".ico", ".bmp", ".gif", ".webp"):
        img = Image.open(path)
    else:
        from icoextract import IconExtractor
        data = IconExtractor(path).get_icon(num=0)
        img = Image.open(io.BytesIO(data.getvalue() if hasattr(data, "getvalue") else data))
    if img.format == "ICO":
        sizes = sorted(img.info.get("sizes", [img.size]), key=lambda s: s[0] * s[1])
        img.size = sizes[-1]
    img.load()
    img.convert("RGBA").save(out)
    return out
