"""Ready made actions (the app library), default pages and credits."""
from __future__ import annotations

import copy

# Who made this. Change these two lines to change the credits everywhere.
AUTHOR = "Ahmed"
STUDIO = "Madhoun"
VERSION = "6.1"


def _a(t, v):
    return {"type": t, "value": v}


def D(name):  # 3D icon
    return f"pack/3d/{name}.png"


def B(name):  # brand tile
    return f"pack/brands/{name}.png"


# exe = where to grab the real app icon (used automatically when the app is installed)
LIBRARY = [
    # Windows
    {"id": "explorer", "cat": "Windows", "name": "File Explorer", "icon": D("file_folder"), "action": _a("open", "explorer.exe")},
    {"id": "downloads", "cat": "Windows", "name": "Downloads", "icon": D("inbox_tray"), "action": _a("open", r"%USERPROFILE%\Downloads")},
    {"id": "settings", "cat": "Windows", "name": "Settings", "icon": D("gear"), "action": _a("open", "ms-settings:")},
    {"id": "taskmgr", "cat": "Windows", "name": "Task Manager", "icon": D("bar_chart"), "action": _a("hotkey", "ctrl+shift+esc")},
    {"id": "screenshot", "cat": "Windows", "name": "Screenshot", "icon": D("camera_with_flash"), "action": _a("hotkey", "win+shift+s")},
    {"id": "clipboard", "cat": "Windows", "name": "Clipboard", "icon": D("clipboard"), "action": _a("hotkey", "win+v")},
    {"id": "emojipanel", "cat": "Windows", "name": "Emoji Panel", "icon": D("grinning_face"), "action": _a("hotkey", "win+.")},
    {"id": "desktop", "cat": "Windows", "name": "Show Desktop", "icon": D("desktop_computer"), "action": _a("hotkey", "win+d")},
    {"id": "taskview", "cat": "Windows", "name": "Task View", "icon": D("card_index_dividers"), "action": _a("hotkey", "win+tab")},
    {"id": "deskleft", "cat": "Windows", "name": "Desktop Left", "icon": D("left_arrow"), "action": _a("hotkey", "ctrl+win+left")},
    {"id": "deskright", "cat": "Windows", "name": "Desktop Right", "icon": D("right_arrow"), "action": _a("hotkey", "ctrl+win+right")},
    {"id": "calc", "cat": "Windows", "name": "Calculator", "icon": D("abacus"), "action": _a("open", "calc.exe")},
    {"id": "notepad", "cat": "Windows", "name": "Notepad", "icon": D("memo"), "action": _a("open", "notepad.exe")},
    {"id": "terminal", "cat": "Windows", "name": "Terminal", "icon": B("ms_terminal"), "action": _a("open", "wt.exe")},
    {"id": "lock", "cat": "Windows", "name": "Lock PC", "icon": D("locked"), "action": _a("command", "rundll32.exe user32.dll,LockWorkStation")},

    # Live tiles and smart keys
    {"id": "nowplaying", "cat": "Live", "name": "Now Playing", "icon": D("musical_note"), "live": "nowplaying",
     "action": _a("np", "toggle"), "double": _a("np", "next"), "hold": _a("np", "previous")},
    {"id": "mic", "cat": "Live", "name": "Microphone", "icon": D("studio_microphone"), "live": "mic", "action": _a("mic", "toggle")},
    {"id": "timer", "cat": "Live", "name": "Focus Timer", "icon": D("timer_clock"), "live": "timer",
     "action": _a("timer", "toggle"), "double": _a("timer", "add5"), "hold": _a("timer", "reset")},
    {"id": "clock", "cat": "Live", "name": "Clock", "icon": D("alarm_clock"), "live": "clock", "action": _a("open", "ms-clock:")},
    {"id": "cpu", "cat": "Live", "name": "CPU usage", "icon": D("bar_chart"), "live": "cpu_usage", "action": _a("hotkey", "ctrl+shift+esc")},
    {"id": "gputemp", "cat": "Live", "name": "GPU temp", "icon": D("thermometer"), "live": "gpu_temp", "action": _a("hotkey", "ctrl+shift+esc")},

    # AI (needs a Claude API key in Settings)
    {"id": "ai_translate", "cat": "AI", "name": "AI Translate", "icon": D("globe_showing_europe_africa"),
     "action": _a("ai", "translate_en"), "double": _a("ai", "translate_pl"), "hold": _a("ai", "translate_ar")},
    {"id": "ai_fix", "cat": "AI", "name": "AI Polish", "icon": D("pencil"), "action": _a("ai", "fix"), "hold": _a("ai", "formal")},
    {"id": "ai_summary", "cat": "AI", "name": "AI Summary", "icon": D("scroll"), "action": _a("ai", "summary"), "hold": _a("ai", "explain")},
    {"id": "ai_reply", "cat": "AI", "name": "AI Reply", "icon": D("speech_balloon"), "action": _a("ai", "reply")},
    {"id": "ai_short", "cat": "AI", "name": "AI Shorter", "icon": D("straight_ruler"), "action": _a("ai", "shorter")},

    # Editing
    {"id": "copy", "cat": "Editing", "name": "Copy", "icon": D("page_facing_up"), "action": _a("hotkey", "ctrl+c")},
    {"id": "paste", "cat": "Editing", "name": "Paste", "icon": D("pushpin"), "action": _a("hotkey", "ctrl+v")},
    {"id": "cut", "cat": "Editing", "name": "Cut", "icon": D("scissors"), "action": _a("hotkey", "ctrl+x")},
    {"id": "undo", "cat": "Editing", "name": "Undo", "icon": D("right_arrow_curving_left"), "action": _a("hotkey", "ctrl+z"), "hold": _a("hotkey", "ctrl+y")},
    {"id": "save", "cat": "Editing", "name": "Save", "icon": D("floppy_disk"), "action": _a("hotkey", "ctrl+s")},
    {"id": "find", "cat": "Editing", "name": "Find", "icon": D("magnifying_glass_tilted_left"), "action": _a("hotkey", "ctrl+f")},
    {"id": "newtab", "cat": "Editing", "name": "New Tab", "icon": D("plus"), "action": _a("hotkey", "ctrl+t")},
    {"id": "closetab", "cat": "Editing", "name": "Close Tab", "icon": D("cross_mark_button"), "action": _a("hotkey", "ctrl+w"), "hold": _a("hotkey", "ctrl+shift+t")},

    # Office & work
    {"id": "outlook", "cat": "Office", "name": "Outlook", "icon": B("ms_outlook"), "badge": "outlook", "action": _a("open", "outlook.exe"), "exe": "outlook.exe"},
    {"id": "calendar", "cat": "Office", "name": "Calendar", "icon": D("spiral_calendar"), "action": _a("open", "outlookcal:")},
    {"id": "teams", "cat": "Office", "name": "Teams", "icon": B("ms_teams"), "action": _a("open", "msteams:")},
    {"id": "excel", "cat": "Office", "name": "Excel", "icon": B("ms_excel"), "action": _a("open", "excel.exe"), "exe": "excel.exe"},
    {"id": "word", "cat": "Office", "name": "Word", "icon": B("ms_word"), "action": _a("open", "winword.exe"), "exe": "winword.exe"},
    {"id": "powerpoint", "cat": "Office", "name": "PowerPoint", "icon": B("ms_powerpoint"), "action": _a("open", "powerpnt.exe"), "exe": "powerpnt.exe"},
    {"id": "onenote", "cat": "Office", "name": "OneNote", "icon": B("ms_onenote"), "action": _a("open", "onenote.exe"), "exe": "onenote.exe"},
    {"id": "powerbi", "cat": "Office", "name": "Power BI", "icon": B("ms_powerbi"), "action": _a("open", "https://app.powerbi.com")},

    # Web
    {"id": "google", "cat": "Web", "name": "Google", "icon": B("google"), "action": _a("open", "https://www.google.com")},
    {"id": "gmail", "cat": "Web", "name": "Gmail", "icon": B("gmail"), "action": _a("open", "https://mail.google.com")},
    {"id": "youtube", "cat": "Web", "name": "YouTube", "icon": B("youtube"), "action": _a("open", "https://www.youtube.com")},
    {"id": "scholar", "cat": "Web", "name": "Scholar", "icon": B("googlescholar"), "action": _a("open", "https://scholar.google.com")},
    {"id": "claude", "cat": "Web", "name": "Claude", "icon": B("claude"), "action": _a("open", "https://claude.ai")},
    {"id": "chatgpt", "cat": "Web", "name": "ChatGPT", "icon": B("chatgpt"), "action": _a("open", "https://chatgpt.com")},
    {"id": "translate", "cat": "Web", "name": "Translate", "icon": B("googletranslate"), "action": _a("open", "https://translate.google.com")},
    {"id": "maps", "cat": "Web", "name": "Maps", "icon": B("googlemaps"), "action": _a("open", "https://maps.google.com")},
    {"id": "github", "cat": "Web", "name": "GitHub", "icon": B("github"), "action": _a("open", "https://github.com")},
    {"id": "whatsapp", "cat": "Web", "name": "WhatsApp", "icon": B("whatsapp"), "action": _a("open", "https://web.whatsapp.com")},
    {"id": "gdrive", "cat": "Web", "name": "Google Drive", "icon": B("googledrive"), "action": _a("open", "https://drive.google.com")},
    {"id": "overleaf", "cat": "Web", "name": "Overleaf", "icon": B("overleaf"), "action": _a("open", "https://www.overleaf.com/project")},

    # Dev & research
    {"id": "vscode", "cat": "Dev", "name": "VS Code", "icon": B("ms_vscode"), "action": _a("command", "code")},
    {"id": "python", "cat": "Dev", "name": "Python", "icon": B("python"), "action": _a("open", "python.exe")},
    {"id": "rstudio", "cat": "Dev", "name": "RStudio", "icon": B("rstudioide"), "action": _a("open", "rstudio.exe"), "exe": "rstudio.exe"},
    {"id": "zotero", "cat": "Dev", "name": "Zotero", "icon": B("zotero"), "action": _a("open", "zotero.exe"), "exe": "zotero.exe"},
    {"id": "cmd", "cat": "Dev", "name": "Command Prompt", "icon": B("ms_terminal"), "action": _a("open", "cmd.exe")},

    # Gaming
    {"id": "steam", "cat": "Gaming", "name": "Steam", "icon": B("steam"), "action": _a("open", "steam://open/main")},
    {"id": "epic", "cat": "Gaming", "name": "Epic Games", "icon": B("epicgames"), "action": _a("open", "com.epicgames.launcher://store")},
    {"id": "discord", "cat": "Gaming", "name": "Discord", "icon": B("discord"), "action": _a("open", "discord://-/channels/@me")},
    {"id": "xboxapp", "cat": "Gaming", "name": "Xbox App", "icon": B("ms_xbox"), "action": _a("open", "xbox:")},
    {"id": "battlenet", "cat": "Gaming", "name": "Battle.net", "icon": B("battledotnet"), "action": _a("open", "battlenet://")},
    {"id": "gamebar", "cat": "Gaming", "name": "Game Bar", "icon": D("video_game"), "action": _a("hotkey", "win+g")},
    {"id": "clip", "cat": "Gaming", "name": "Clip That", "icon": D("clapper_board"), "action": _a("hotkey", "win+alt+g")},
    {"id": "record", "cat": "Gaming", "name": "Record", "icon": D("red_circle"), "action": _a("hotkey", "win+alt+r")},
    {"id": "gameshot", "cat": "Gaming", "name": "Game Screenshot", "icon": D("camera_with_flash"), "action": _a("hotkey", "win+alt+printscreen")},
    {"id": "dmute", "cat": "Gaming", "name": "Discord Mute", "icon": D("studio_microphone"), "action": _a("hotkey", "ctrl+shift+m"), "hold": _a("hotkey", "ctrl+shift+d")},
    {"id": "nvoverlay", "cat": "Gaming", "name": "NVIDIA Overlay", "icon": B("nvidia"), "action": _a("hotkey", "alt+z")},
    {"id": "twitch", "cat": "Gaming", "name": "Twitch", "icon": B("twitch"), "action": _a("open", "https://www.twitch.tv")},

    # Media
    {"id": "spotify", "cat": "Media", "name": "Spotify", "icon": B("spotify"), "action": _a("open", "spotify:")},
    {"id": "netflix", "cat": "Media", "name": "Netflix", "icon": B("netflix"), "action": _a("open", "https://www.netflix.com")},
    {"id": "playpause", "cat": "Media", "name": "Play / Pause", "icon": D("play_or_pause_button"), "action": _a("media", "play_pause")},
    {"id": "next", "cat": "Media", "name": "Next Track", "icon": D("next_track_button"), "action": _a("media", "next")},
    {"id": "prev", "cat": "Media", "name": "Previous", "icon": D("last_track_button"), "action": _a("media", "previous")},
    {"id": "mute", "cat": "Media", "name": "Mute", "icon": D("muted_speaker"), "action": _a("media", "mute")},
    {"id": "volup", "cat": "Media", "name": "Volume Up", "icon": D("speaker_high_volume"), "action": _a("media", "volume_up")},
    {"id": "voldown", "cat": "Media", "name": "Volume Down", "icon": D("speaker_medium_volume"), "action": _a("media", "volume_down")},

    # Meetings (Teams shortcuts)
    {"id": "camera", "cat": "Meeting", "name": "Camera", "icon": D("video_camera"), "action": _a("hotkey", "ctrl+shift+o")},
    {"id": "hand", "cat": "Meeting", "name": "Raise Hand", "icon": D("bell"), "action": _a("hotkey", "ctrl+shift+k")},
    {"id": "share", "cat": "Meeting", "name": "Share Screen", "icon": D("desktop_computer"), "action": _a("hotkey", "ctrl+shift+e")},
    {"id": "leave", "cat": "Meeting", "name": "Leave Call", "icon": D("telephone_receiver"), "action": _a("hotkey", "ctrl+shift+h")},
    {"id": "notes", "cat": "Meeting", "name": "Quick Notes", "icon": D("spiral_notepad"), "action": _a("open", "notepad.exe")},

    # Excel
    {"id": "xsum", "cat": "Excel", "name": "AutoSum", "icon": D("abacus"), "action": _a("hotkey", "alt+=")},
    {"id": "xfilter", "cat": "Excel", "name": "Filter", "icon": D("magnifying_glass_tilted_left"), "action": _a("hotkey", "ctrl+shift+l")},
    {"id": "xformat", "cat": "Excel", "name": "Format Cells", "icon": D("artist_palette"), "action": _a("hotkey", "ctrl+1")},
    {"id": "xinsert", "cat": "Excel", "name": "Insert Row", "icon": D("plus"), "action": _a("hotkey", "ctrl+shift+plus")},
    {"id": "xdelete", "cat": "Excel", "name": "Delete Row", "icon": D("minus"), "action": _a("hotkey", "ctrl+minus")},
    {"id": "xsheet", "cat": "Excel", "name": "New Sheet", "icon": D("ledger"), "action": _a("hotkey", "shift+f11")},

    # Arcade
    {"id": "simon", "cat": "Arcade", "name": "Simon", "icon": D("joystick"), "action": _a("game", "simon")},
    {"id": "reaction", "cat": "Arcade", "name": "Reaction", "icon": D("high_voltage"), "action": _a("game", "reaction")},
    {"id": "dice", "cat": "Arcade", "name": "Roll Dice", "icon": D("game_die"), "action": _a("fun", "dice")},
    {"id": "coin", "cat": "Arcade", "name": "Flip Coin", "icon": D("coin"), "action": _a("fun", "coin")},
    {"id": "party", "cat": "Arcade", "name": "Party Mode", "icon": D("party_popper"), "action": _a("fun", "party")},

    # Deck
    {"id": "pagenext", "cat": "Deck", "name": "Next Page", "icon": D("right_arrow"), "action": _a("page", "next")},
    {"id": "pageprev", "cat": "Deck", "name": "Prev Page", "icon": D("left_arrow"), "action": _a("page", "prev")},
    {"id": "pagehome", "cat": "Deck", "name": "Home Page", "icon": D("house"), "action": _a("page", "1")},

    # Macros
    {"id": "m_start", "cat": "Macros", "name": "Start My Day", "icon": D("sun"),
     "action": {"type": "macro", "value": "", "steps": [_a("open", "outlook.exe"), _a("wait", "800"), _a("open", "msteams:"),
                                                         _a("wait", "800"), _a("open", "outlookcal:"), _a("page", "Work")]}},
    {"id": "m_game", "cat": "Macros", "name": "Game Night", "icon": D("video_game"),
     "action": {"type": "macro", "value": "", "steps": [_a("open", "discord://-/channels/@me"), _a("wait", "1500"),
                                                         _a("open", "steam://open/main"), _a("page", "Gaming")]}},
    {"id": "m_focus", "cat": "Macros", "name": "Focus Mode", "icon": D("headphone"),
     "action": {"type": "macro", "value": "", "steps": [_a("hotkey", "win+d"), _a("open", "spotify:"), _a("wait", "1500"),
                                                         _a("timer", "start"), _a("page", "Assistant")]}},
]

EMOJIS = ("🏠 📁 🌐 🔍 📧 📅 👥 📊 📈 📗 📘 📙 📓 🎓 ✨ 💬 🌍 🗺️ 💻 ⌨️ 🧮 📝 📋 📌 "
          "✂️ 🔒 ⚙️ 🖥️ 🗂️ 📥 🎵 🎧 🎙️ 🔇 🔊 ⏯️ ⏭️ ⏮️ 📷 🎬 🎮 ☕ 💡 🚀 ⭐ ❤️ 🔥 ✅ "
          "❌ ⏰ 🔋 🌙 ☀️ 🧠 📚 🧪 🛒 💰 🏋️ ✈️ 🎨 🐙 🕹️ 👾 🎯 🏆 ⚔️ 🌡️ 📡 🛰️").split()

ACCENTS = ["#7c5cff", "#2f80ed", "#14b8a6", "#ec4899", "#f97316", "#22c55e", "#eab308", "#ef4444"]

_BY_ID = {i["id"]: i for i in LIBRARY}
_BY_NAME = {i["name"].lower(): i for i in LIBRARY}


def key_from(item_id: str) -> dict:
    it = _BY_ID[item_id]
    k = {"label": it["name"], "emoji": "", "icon": it.get("icon", ""), "bg": "none", "show_label": False,
         "icon_scale": 0.9, "action": copy.deepcopy(it["action"]), "exe": it.get("exe", ""),
         "icon_auto": bool(it.get("exe"))}
    for g in ("double", "hold"):
        if it.get(g):
            k[g] = copy.deepcopy(it[g])
    if it.get("live"):
        k["live"] = it["live"]
    if it.get("badge"):
        k["badge"] = it["badge"]
    return k


def blank_key() -> dict:
    return {"label": "", "emoji": "", "icon": "", "bg": "none", "show_label": False,
            "icon_scale": 0.9, "action": _a("none", "")}


def page(name, emoji, accent, ids, rgb=False, apps=None, games=False, hidden=False):
    return {"name": name, "emoji": emoji, "accent": accent, "wallpaper": "", "rgb": rgb,
            "apps": apps or [], "games": games, "hidden": hidden,
            "keys": {str(i): key_from(x) if x else blank_key() for i, x in enumerate(ids)}}


def blank_page(n: int) -> dict:
    return {"name": f"Page {n}", "emoji": "✨", "accent": ACCENTS[(n - 1) % len(ACCENTS)], "wallpaper": "",
            "rgb": False, "apps": [], "games": False, "hidden": False,
            "keys": {str(i): blank_key() for i in range(6)}}


def live_key(metric: str, label: str) -> dict:
    k = blank_key()
    k.update(label=label, live=metric, action=_a("hotkey", "ctrl+shift+esc"))
    return k


def gaming_page():
    return page("Gaming", "🎮", "#22c55e", ["steam", "epic", "discord", "gamebar", "clip", "dmute"], rgb=True, games=True)


def system_page():
    p = page("System", "🌡️", "#06b6d4", [None] * 6)
    for i, (m, lbl) in enumerate([("cpu_usage", "CPU usage"), ("cpu_temp", "CPU temp"), ("gpu_usage", "GPU usage"),
                                  ("gpu_temp", "GPU temp"), ("ram", "RAM"), ("net_down", "Download")]):
        p["keys"][str(i)] = live_key(m, lbl)
    return p


def assistant_page():
    return page("Assistant", "✨", "#a855f7", ["timer", "ai_translate", "ai_fix", "ai_summary", "ai_reply", "claude"])


def arcade_page():
    return page("Arcade", "🕹️", "#f97316", ["simon", "reaction", "dice", "coin", "party", "pagehome"], rgb=True)


def meeting_page():
    return page("Meeting", "📞", "#ef4444", ["mic", "camera", "hand", "share", "notes", "leave"],
                apps=["ms-teams.exe", "teams.exe", "zoom.exe"], hidden=True)


def excel_page():
    return page("Excel", "📗", "#16a34a", ["xsum", "xfilter", "xformat", "xinsert", "xdelete", "xsheet"],
                apps=["excel.exe"], hidden=True)


def media_page():
    return page("Media", "🎧", "#ec4899", ["nowplaying", "spotify", "youtube", "prev", "playpause", "next"])


DEFAULT_KNOBS = {
    # 1 = big knob: press to switch mode, hold for the mode's extra (mute...)
    "1": {"label": "Dial", "modes": ["volume", "app_media", "brightness", "scrub"], "mode": 0,
          "left": _a("media", "volume_down"), "right": _a("media", "volume_up"), "press": _a("media", "mute")},
    "0": {"label": "Scroll", "left": _a("scroll", "-3"), "right": _a("scroll", "3"), "press": _a("hotkey", "win+tab")},
    "2": {"label": "Zoom", "left": _a("hotkey", "ctrl+minus"), "right": _a("hotkey", "ctrl+plus"), "press": _a("hotkey", "ctrl+0")},
}


def default_config() -> dict:
    return {
        "version": 5,
        "brightness": 80,
        "splash": True,
        "timer_minutes": 25,
        "smart": {"enabled": True, "go_back": True},
        "current_page": 0,
        "pages": [
            page("Home", "🏠", "#7c5cff", ["explorer", "google", "screenshot", "taskmgr", "calc", "lock"]),
            page("Work", "💼", "#2f80ed", ["outlook", "teams", "excel", "word", "powerpoint", "calendar"]),
            page("Research", "🎓", "#14b8a6", ["scholar", "claude", "overleaf", "zotero", "downloads", "vscode"]),
            assistant_page(),
            gaming_page(),
            system_page(),
            media_page(),
            arcade_page(),
            meeting_page(),
            excel_page(),
        ],
        # The 3 round buttons under the screens (same on every page)
        "buttons": {
            "0": {"label": "Previous page", "action": _a("page", "prev"), "hold": _a("page", "1")},
            "1": {"label": "Play / Pause", "action": _a("np", "toggle"), "double": _a("np", "next"), "hold": _a("mic", "toggle")},
            "2": {"label": "Next page", "action": _a("page", "next")},
        },
        "knobs": copy.deepcopy(DEFAULT_KNOBS),
        "stats": {"presses": {}, "best": {}},
    }


def upgrade_v5(cfg: dict) -> dict:
    """Bring an older setup up to date without losing anything the user made."""
    names = {p.get("name", "").lower() for p in cfg.get("pages", [])}
    for maker in (assistant_page, arcade_page, meeting_page, excel_page):
        p = maker()
        if p["name"].lower() not in names:
            cfg.setdefault("pages", []).append(p)
    for p in cfg.get("pages", []):
        p.setdefault("apps", [])
        p.setdefault("hidden", False)
        if p.get("name") == "Gaming":
            p.setdefault("games", True)
        if p.get("name") == "Media" and p["keys"].get("0", {}).get("label") == "Spotify" and not any(
                k.get("live") == "nowplaying" for k in p["keys"].values()):
            p["keys"]["0"] = key_from("nowplaying")
        for k in p.get("keys", {}).values():  # give old keys the new pro icons
            it = _BY_NAME.get((k.get("label") or "").lower())
            if it and not k.get("icon") and it.get("icon"):
                k["icon"] = it["icon"]
                if it.get("exe"):
                    k["exe"], k["icon_auto"] = it["exe"], True
            if it and it.get("badge") and "badge" not in k:
                k["badge"] = it["badge"]
    big = cfg.get("knobs", {}).get("1", {})
    if big.get("label") == "Volume" and not big.get("modes"):
        cfg["knobs"]["1"] = copy.deepcopy(DEFAULT_KNOBS["1"])
    b1 = cfg.get("buttons", {}).get("1", {})
    if b1.get("label") == "Play / Pause" and "double" not in b1:
        cfg["buttons"]["1"] = default_config()["buttons"]["1"]
    cfg.setdefault("smart", {"enabled": True, "go_back": True})
    cfg.setdefault("timer_minutes", 25)
    cfg.setdefault("stats", {"presses": {}, "best": {}})
    cfg["version"] = 5
    return cfg
