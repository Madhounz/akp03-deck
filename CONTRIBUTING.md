# Contributing

Thanks for wanting to help! This is a small project, so the process is simple.

## Reporting a bug

Open an issue with the Bug report form. Please attach `akp03.log` and `launcher.log` from the app folder
and tell us which device and Windows version you use.

## Running from source

```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pip install -r optional.txt
.venv\Scripts\python app.py
```

`python akp03.py` on its own is a quick hardware test: it paints the keys and prints every press.

## Where things live

| File | What it does |
|---|---|
| `akp03.py` | USB driver. One thread owns the device. Keep all device I/O in here. |
| `core.py` | Pages, gestures, knob modes, smart pages, live tiles, games |
| `render.py` | Draws key images with Pillow |
| `library.py` | Ready made actions, default pages, credits |
| `actions.py` | Runs hotkeys, media keys, apps, commands |
| `media.py`, `monitor.py`, `context.py` | Windows integrations, PC stats, foreground app |
| `app.py` | Local web server, tray icon, startup |
| `flyout.py` | Quick panel by the clock |
| `ui/` | The studio (plain HTML, CSS and JavaScript, no build step) |
| `pack/` | Icons and their manifest |

## Pull requests

- Keep it working without the optional packages. Every Windows extra should fail quietly.
- Never write to the device outside `akp03.py`.
- Test on real hardware if you can, and say which device you used.
- New library actions go in `library.py` with an icon from `pack/`.

Adding support for a new device is often just a line in `KNOWN_IDS` in `akp03.py`. Please include the
output of `python app.py --list` in the pull request.
