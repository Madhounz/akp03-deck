"""Actions that a key, button or knob can trigger."""
from __future__ import annotations

import os
import subprocess
import sys
import webbrowser

from pynput.keyboard import Controller as KB, Key
from pynput.mouse import Controller as Mouse

kb = KB()
mouse = Mouse()

ACTION_TYPES = ["none", "open", "hotkey", "media", "np", "page", "macro", "ai", "timer", "mic", "game", "fun", "command", "text", "scroll"]

MEDIA = {
    "play_pause": Key.media_play_pause,
    "next": Key.media_next,
    "previous": Key.media_previous,
    "volume_up": Key.media_volume_up,
    "volume_down": Key.media_volume_down,
    "mute": Key.media_volume_mute,
}

HINTS = {
    "none": "Does nothing",
    "open": "App, file, folder, URL (https://...) or app link like spotify:",
    "hotkey": "Example: ctrl+shift+m, alt+tab, win+v, f5",
    "media": "Play/pause, tracks and volume",
    "page": "next, prev, a page number, or a page name",
    "command": "Any Windows command, e.g. shutdown /s /t 0",
    "text": "Types this text for you",
    "scroll": "Lines to scroll: positive = up, negative = down",
    "np": "Controls whatever is playing: toggle, next or previous",
    "macro": "Runs several steps in a row",
    "ai": "Select text anywhere, press the key, Claude does the rest",
    "timer": "toggle, add5, reset, start or set:25",
    "mic": "Mutes or unmutes your microphone everywhere",
    "game": "simon or reaction. Any round button quits",
    "fun": "dice, coin or party",
}

SUGGESTIONS = {
    "media": list(MEDIA),
    "hotkey": ["ctrl+c", "ctrl+v", "ctrl+z", "win+shift+s", "win+v", "win+d", "win+tab",
               "ctrl+shift+esc", "win+alt+k", "ctrl+win+left", "ctrl+win+right", "ctrl+plus", "ctrl+minus"],
    "open": ["explorer.exe", "calc.exe", "notepad.exe", "ms-settings:", "spotify:", "https://www.google.com",
             r"%USERPROFILE%\Downloads"],
    "page": ["next", "prev", "1", "2", "3"],
    "command": ["rundll32.exe user32.dll,LockWorkStation"],
    "scroll": ["3", "-3", "1", "-1"],
    "np": ["toggle", "next", "previous"],
    "timer": ["toggle", "add5", "reset", "start", "set:25", "set:50"],
    "mic": ["toggle"],
    "game": ["simon", "reaction"],
    "fun": ["dice", "coin", "party"],
}

_NAMED = {
    "ctrl": Key.ctrl, "control": Key.ctrl, "shift": Key.shift, "alt": Key.alt,
    "win": Key.cmd, "cmd": Key.cmd, "enter": Key.enter, "return": Key.enter,
    "tab": Key.tab, "esc": Key.esc, "escape": Key.esc, "space": Key.space,
    "backspace": Key.backspace, "delete": Key.delete, "del": Key.delete,
    "home": Key.home, "end": Key.end, "pageup": Key.page_up, "pagedown": Key.page_down,
    "up": Key.up, "down": Key.down, "left": Key.left, "right": Key.right,
    "insert": Key.insert, "printscreen": Key.print_screen, "capslock": Key.caps_lock,
    "plus": "=", "minus": "-",
}
_NAMED.update({f"f{i}": getattr(Key, f"f{i}") for i in range(1, 21)})

_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _parse_hotkey(text: str):
    keys = []
    for part in text.lower().replace(" ", "").split("+"):
        if not part:
            continue
        if part in _NAMED:
            keys.append(_NAMED[part])
        elif len(part) == 1:
            keys.append(part)
        else:
            raise ValueError(f"Unknown key: {part}")
    return keys


def run(action: dict | None) -> None:
    """Run one action. Page actions are handled by the core, not here."""
    if not action:
        return
    t = action.get("type", "none")
    v = os.path.expandvars(str(action.get("value", "")).strip())
    try:
        if t == "hotkey" and v:
            keys = _parse_hotkey(v)
            for k in keys:
                kb.press(k)
            for k in reversed(keys):
                kb.release(k)
        elif t == "media" and v in MEDIA:
            kb.press(MEDIA[v]); kb.release(MEDIA[v])
        elif t == "open" and v:
            if v.startswith(("http://", "https://")):
                webbrowser.open(v)
            else:
                os.startfile(v.strip('"'))  # Windows only
        elif t == "command" and v:
            subprocess.Popen(v, shell=True, creationflags=_NO_WINDOW)
        elif t == "text" and v:
            kb.type(v)
        elif t == "scroll" and v:
            mouse.scroll(0, int(v))
    except Exception as e:  # one bad action must never crash the deck
        print(f"Action failed ({t}: {v}): {e}")
