"""Which app is in front, so pages can follow you (Windows only)."""
from __future__ import annotations

import ctypes
import os

import psutil

GAME_PATHS = ("steamapps\\common", "epic games", "riot games", "battle.net", "ubisoft game launcher\\games",
              "ea games", "gog galaxy\\games", "xboxgames", "windowsapps\\microsoft.minecraft")
LAUNCHERS = {"steam.exe", "steamwebhelper.exe", "epicgameslauncher.exe", "riotclientservices.exe", "battle.net.exe"}


def foreground() -> tuple[str, str, str]:
    """(exe name, exe path, window title) of the window in front."""
    if os.name != "nt":
        return "", "", ""
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        p = psutil.Process(pid.value)
        try:
            path = p.exe()
        except Exception:
            path = ""
        return p.name().lower(), path.lower(), buf.value
    except Exception:
        return "", "", ""


def is_game(exe: str, path: str) -> bool:
    return exe not in LAUNCHERS and any(g in path for g in GAME_PATHS)


def running_apps() -> list[str]:
    """Apps that have a visible window, for picking in the studio."""
    if os.name != "nt":
        return []
    user32 = ctypes.windll.user32
    pids = set()
    proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0:
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            pids.add(pid.value)
        return True

    user32.EnumWindows(proc(cb), 0)
    names = set()
    for pid in pids:
        try:
            names.add(psutil.Process(pid).name().lower())
        except Exception:
            pass
    skip = {"explorer.exe", "textinputhost.exe", "applicationframehost.exe", "systemsettings.exe", "pythonw.exe", "python.exe"}
    return sorted(names - skip)
