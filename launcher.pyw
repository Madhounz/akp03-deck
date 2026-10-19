"""Keeps AKP03 Deck running.

Windows starts this file at login. It starts the app, checks every 20 seconds that the app
still answers, and restarts it if it crashed or hung. Choosing Quit in the app stops it for good.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
import urllib.request
from logging.handlers import RotatingFileHandler

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 47613
CHECK_S = 20          # how often to check the app is alive
MISSES_TO_RESTART = 3  # about a minute of no answer = hung
BOOT_DELAY_S = 6      # at login, give USB and the desktop a moment

h = RotatingFileHandler(os.path.join(HERE, "launcher.log"), maxBytes=128_000, backupCount=1, encoding="utf-8")
h.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%Y-%m-%d %H:%M:%S"))
log = logging.getLogger("launcher")
log.setLevel(logging.INFO)
log.addHandler(h)


def alive() -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/alive", timeout=4) as r:
            return r.status == 200
    except Exception:
        return False


def pythonw() -> str:
    exe = sys.executable
    if exe.lower().endswith("python.exe") and os.path.exists(exe[:-10] + "pythonw.exe"):
        return exe[:-10] + "pythonw.exe"
    return exe


def start(minimized: bool) -> subprocess.Popen:
    args = [pythonw(), os.path.join(HERE, "app.py")]
    if minimized:
        args.append("--minimized")
    flags = 0x08000000 if os.name == "nt" else 0  # no console window
    return subprocess.Popen(args, cwd=HERE, creationflags=flags)


def main():
    boot = "--boot" in sys.argv
    if alive():
        if not boot:  # opened by hand while running: just show the quick panel
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/poke", timeout=3).read()
            except Exception:
                pass
        return
    if boot:
        time.sleep(BOOT_DELAY_S)

    crashes: list[float] = []
    minimized = boot
    while True:
        log.info("Starting app")
        p = start(minimized)
        minimized = True  # restarts are always quiet
        misses = 0
        while True:
            try:
                code = p.wait(timeout=CHECK_S)
                break
            except subprocess.TimeoutExpired:
                pass
            if alive():
                misses = 0
                continue
            misses += 1
            if misses >= MISSES_TO_RESTART:
                log.info("App stopped answering, restarting it")
                p.kill()
                p.wait()
                code = -1
                break
        if code == 0:
            log.info("App closed normally")
            return
        now = time.time()
        crashes = [t for t in crashes if now - t < 600] + [now]
        log.info("App exited with code %s", code)
        if len(crashes) >= 6:
            log.info("Too many crashes in 10 minutes, giving up. Check akp03.log")
            return
        time.sleep(min(60, 3 * len(crashes)))


if __name__ == "__main__":
    main()
