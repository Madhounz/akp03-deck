"""Quick panel that pops up next to the clock when you click the tray icon.

Built on Tk (already part of Python) and drawn by hand on one canvas, so it costs a few MB
and does no work at all while it is hidden.
"""
from __future__ import annotations

import ctypes
import os
import threading
import time
import tkinter as tk
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter, ImageOps, ImageTk

import icons
import library
import render

KEY = "#010203"          # see-through color for the rounded corners
BG_TOP, BG_BOT = (31, 33, 40), (20, 21, 26)
CARD = (37, 40, 48)
LINE = (52, 56, 66)
TEXT = "#eceef2"
MUTED = "#959cab"
FONT = "Segoe UI Variable Display"
FONT_TXT = "Segoe UI Variable Text"


def _hex(c, fallback=(124, 92, 255)):
    try:
        c = c.lstrip("#")
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return fallback


def _rgb(t):
    return "#%02x%02x%02x" % tuple(t[:3])


@lru_cache(maxsize=96)
def rrect(w, h, r, fill, outline=None, width=1):
    """Antialiased rounded rectangle as RGBA (drawn at 3x, then shrunk)."""
    S = 3
    img = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w * S - 1, h * S - 1), radius=r * S, fill=fill,
                        outline=outline, width=width * S if outline else 0)
    return img.resize((w, h), Image.LANCZOS)


@lru_cache(maxsize=8)
def circle(d, fill, outline=None, width=1):
    S = 3
    img = Image.new("RGBA", (d * S, d * S), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((0, 0, d * S - 1, d * S - 1), fill=fill, outline=outline,
                                width=width * S if outline else 0)
    return img.resize((d, d), Image.LANCZOS)


def rounded(img, r):
    S = 3
    m = Image.new("L", (img.width * S, img.height * S), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, img.width * S - 1, img.height * S - 1), radius=r * S, fill=255)
    out = img.convert("RGBA")
    out.putalpha(m.resize(img.size, Image.LANCZOS))
    return out


@lru_cache(maxsize=40)
def icon3d(name, px):
    im = render.load_icon(icons.p3d(name))
    if im is None:
        return Image.new("RGBA", (px, px), (0, 0, 0, 0))
    return ImageOps.contain(im, (px, px), Image.LANCZOS)


@lru_cache(maxsize=24)
def emoji_icon(ch, px):
    im = render.emoji_image(ch or "✨")
    if im is None:
        return Image.new("RGBA", (px, px), (0, 0, 0, 0))
    return ImageOps.contain(im, (px, px), Image.LANCZOS)


@lru_cache(maxsize=4)
def background(w, h, r, accent):
    ar, ag, ab = _hex(accent)
    S = 2
    W, H = w * S, h * S
    grad = Image.new("RGB", (1, H))
    for y in range(H):
        t = y / max(1, H - 1)
        grad.putpixel((0, y), tuple(int(BG_TOP[i] + (BG_BOT[i] - BG_TOP[i]) * t) for i in range(3)))
    img = grad.resize((W, H))
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse((W * 0.05, -H * 0.16, W * 0.95, H * 0.16), fill=70)
    glow = glow.filter(ImageFilter.GaussianBlur(W * 0.12))
    img = Image.composite(Image.new("RGB", (W, H), (ar, ag, ab)), img, glow)
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, W - 1, H - 1), radius=r * S, fill=255)
    out = Image.new("RGB", (W, H), _hex(KEY))
    out.paste(img, (0, 0), mask)
    ImageDraw.Draw(out).rounded_rectangle((0, 0, W - 1, H - 1), radius=r * S, outline=LINE, width=S)
    return out.resize((w, h), Image.NEAREST)  # NEAREST keeps the see-through corners clean


class Flyout:
    WIDTH = 384

    def __init__(self, core, open_studio, quit_app):
        self.core = core
        self.open_studio = open_studio
        self.quit_app = quit_app
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("AKP03 Deck")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=KEY)
        try:
            self.root.attributes("-transparentcolor", KEY)
        except tk.TclError:
            pass
        self.k = max(1.0, self.root.winfo_fpixels("1i") / 96.0)
        self.cv = tk.Canvas(self.root, highlightthickness=0, bd=0, bg=KEY)
        self.cv.pack()
        self.visible = False
        self.startup = None        # (get, set) for "start with Windows", given by app.py
        self._autostart = None
        self._hidden_at = 0.0
        self._refs = []
        self.hits = []
        self.hover = None
        self.drag = None
        self.pressed = None
        self._vol = (0.0, None)
        self._screen = None
        self._save_job = None
        self._job = None
        self.cv.bind("<Motion>", self._motion)
        self.cv.bind("<Leave>", lambda e: self._set_hover(None))
        self.cv.bind("<Button-1>", self._down)
        self.cv.bind("<B1-Motion>", self._drag)
        self.cv.bind("<ButtonRelease-1>", self._up)
        self.root.bind("<Escape>", lambda e: self.hide())
        self.root.bind("<FocusOut>", lambda e: self.root.after(120, self._check_focus))
        self._rounded_corners()

    # ---------------- window ----------------
    def s(self, v):
        return int(round(v * self.k))

    def _rounded_corners(self):
        try:
            self.root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            pref = ctypes.c_int(2)  # Windows 11: round corners
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(pref), 4)
        except Exception:
            pass

    def _work_area(self):
        try:
            class RECT(ctypes.Structure):
                _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]
            rc = RECT()
            ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(rc), 0)
            return rc.l, rc.t, rc.r, rc.b
        except Exception:
            return 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight() - 48

    def toggle(self):
        if self.visible:
            self.hide()
        elif time.time() - self._hidden_at > 0.35:  # the click on the tray icon just closed it
            self.show()

    def show(self):
        self.visible = True
        self.core.flyout_open = True
        self._vol = (0.0, None)
        self._autostart = None
        threading.Thread(target=self._read_screen, daemon=True).start()
        w, h = self.draw()
        l, t, r, b = self._work_area()
        top_bar = t > 0 and b >= self.root.winfo_screenheight() - 2
        x = r - w - self.s(12)
        y_end = t + self.s(12) if top_bar else b - h - self.s(12)
        y0 = y_end + (-self.s(14) if top_bar else self.s(14))
        self.root.geometry(f"{w}x{h}+{x}+{y0}")
        try:
            self.root.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self._rounded_corners()

        def anim(step=0, n=9):
            f = 1 - (1 - step / n) ** 3
            try:
                self.root.attributes("-alpha", f)
            except tk.TclError:
                pass
            self.root.geometry(f"+{x}+{int(y0 + (y_end - y0) * f)}")
            if step < n:
                self.root.after(14, anim, step + 1, n)
        anim()
        self._schedule()

    def hide(self):
        if not self.visible:
            return
        self.visible = False
        self.core.flyout_open = False
        self._hidden_at = time.time()
        self.root.withdraw()
        if self._job:
            self.root.after_cancel(self._job)
            self._job = None
        self._refs = []

    def _check_focus(self):
        if self.visible and self.drag is None and self.root.focus_get() is None:
            self.hide()

    def _schedule(self):
        if not self.visible:
            return
        if self.drag is None:
            self.draw()
        self._job = self.root.after(450, self._schedule)

    def _read_screen(self):
        self._screen = self.core.bright.current()

    # ---------------- drawing helpers ----------------
    def _img(self, x, y, pil, anchor="nw"):
        p = ImageTk.PhotoImage(pil)
        self._refs.append(p)
        self.cv.create_image(self.s(x), self.s(y), image=p, anchor=anchor)

    def _box(self, x, y, w, h, r, fill, outline=None, width=1):
        self._img(x, y, rrect(self.s(w), self.s(h), self.s(r), fill, outline, width))

    def _text(self, x, y, t, size=10, bold=False, color=TEXT, anchor="nw", family=FONT_TXT, width=None):
        kw = {"width": self.s(width)} if width else {}
        self.cv.create_text(self.s(x), self.s(y), text=t, fill=color, anchor=anchor,
                            font=(family, size, "bold" if bold else "normal"), **kw)

    def _fit(self, t, size, bold, maxw):
        """Shorten text with an ellipsis so it fits maxw (logical px)."""
        import tkinter.font as tkf
        f = tkf.Font(family=FONT_TXT, size=size, weight="bold" if bold else "normal")
        lim = self.s(maxw)
        if f.measure(t) <= lim:
            return t
        while t and f.measure(t + "…") > lim:
            t = t[:-1]
        return t + "…"

    def _hit(self, x, y, w, h, name, cb=None, drag=None):
        self.hits.append((self.s(x), self.s(y), self.s(x + w), self.s(y + h), name, cb, drag))

    def _pill(self, x, y, w, h, label, name, cb, primary=False):
        acc = _hex(self.accent)
        hov = self.hover == name
        if primary:
            fill = tuple(min(255, c + 22) for c in acc) if hov else acc
            self._box(x, y, w, h, h // 2, fill + (255,))
        else:
            self._box(x, y, w, h, h // 2, (52, 56, 66, 255) if hov else CARD + (255,), LINE + (255,))
        self._text(x + w / 2, y + h / 2, label, 9, True, "#ffffff" if primary else TEXT, "center")
        self._hit(x, y, w, h, name, cb)

    def _icon_btn(self, x, y, size, pil, name, cb, active=False):
        hov = self.hover == name
        if hov or active:
            self._box(x - 4, y - 4, size + 8, size + 8, 10, (255, 255, 255, 26 if hov else 18))
        self._img(x, y, pil.resize((self.s(size), self.s(size)), Image.LANCZOS) if pil.width != self.s(size) else pil)
        self._hit(x - 4, y - 4, size + 8, size + 8, name, cb)

    # ---------------- the panel ----------------
    def draw(self):
        c = self.core
        cfg = c.cfg
        p = c.page_index
        page = cfg["pages"][p]
        self.accent = page.get("accent", "#7c5cff")
        acc = _hex(self.accent)
        W, P = self.WIDTH, 18
        CW = W - 2 * P
        show_vol = c.audio.ok
        show_screen = c.bright.sbc is not None
        n_sliders = 1 + int(show_vol) + int(show_screen)
        H = 572 + n_sliders * 38

        self.cv.delete("all")
        self._refs = []
        self.hits = []
        self.cv.config(width=self.s(W), height=self.s(H))
        self._img(0, 0, background(self.s(W), self.s(H), self.s(18), self.accent))

        # header
        self._img(P, 18, render.app_icon(self.s(32)))
        self._text(P + 42, 18, "AKP03 Deck", 12, True, family=FONT)
        st = c.health["state"]
        dot, label = {"connected": ("#3ddc84", "Deck connected"), "reconnecting": ("#f5a524", "Reconnecting…")}.get(
            st, ("#f5a524", "Plug in your deck"))
        self._img(P + 42, 41, circle(self.s(8), dot))
        self._text(P + 55, 37, label, 9, color=MUTED)
        if st != "connected":
            self._pill(W - P - 168, 22, 86, 28, "Reconnect", "reconnect", c.reconnect)
        self._pill(W - P - 76, 22, 76, 28, "Studio", "studio", self._studio, primary=True)

        # pages
        y = 70
        pages = [(i, pg) for i, pg in enumerate(cfg["pages"]) if not pg.get("hidden") or i == p][:8]
        chip, gap = 38, 6
        for j, (i, pg) in enumerate(pages):
            x = P + j * (chip + gap)
            on = i == p
            hov = self.hover == f"pg{i}"
            if on:
                self._box(x, y, chip, chip, 12, (*acc, 70), (*acc, 255), 2)
            else:
                self._box(x, y, chip, chip, 12, (52, 56, 66, 255) if hov else CARD + (255,))
            self._img(x + chip / 2, y + chip / 2, emoji_icon(pg.get("emoji", "✨"), self.s(24)), "center")
            self._hit(x, y, chip, chip, f"pg{i}", lambda i=i: c.goto_page(i))
        auto = " · opened by itself" if c._auto else ""
        self._text(P, 118, f"{page.get('name', 'Page').upper()}{auto}", 8, True, MUTED, family=FONT)

        # mini deck (live, clickable)
        y = 138
        self._box(P, y, CW, 216, 16, (10, 11, 14, 255), (40, 43, 52, 255))
        ks, kg = 94, 12
        x0 = P + (CW - (3 * ks + 2 * kg)) / 2
        for i in range(6):
            kx, ky = x0 + (i % 3) * (ks + kg), y + 12 + (i // 3) * (ks + kg)
            try:
                im = c.key_image(p, i, self.s(ks - 8))
            except Exception:
                im = Image.new("RGB", (self.s(ks - 8), self.s(ks - 8)))
            hov = self.hover == f"k{i}"
            ring = (*acc, 255) if hov else (34, 37, 44, 255)
            self._box(kx, ky, ks, ks, 14, (16, 17, 21, 255), ring, 2 if hov else 1)
            if self.pressed == f"k{i}":
                im = Image.blend(im.convert("RGB"), Image.new("RGB", im.size, (255, 255, 255)), 0.25)
            self._img(kx + 4, ky + 4, rounded(im, self.s(10)))
            self._hit(kx, ky, ks, ks, f"k{i}", lambda i=i: self._press_key(i))

        # now playing
        y = 368
        np = c.np.info if c.np.ok else {}
        self._box(P, y, CW, 76, 16, CARD + (255,))
        art = np.get("art")
        if art is not None:
            self._img(P + 10, y + 10, rounded(ImageOps.fit(art, (self.s(56), self.s(56)), Image.LANCZOS), self.s(10)))
        else:
            self._box(P + 10, y + 10, 56, 56, 10, (22, 24, 29, 255))
            self._img(P + 38, y + 38, icon3d("musical_note", self.s(32)), "center")
        title = np.get("title") or ("Nothing playing" if c.np.ok else "Media info needs setup")
        artist = np.get("artist") or ("Play something to see it here" if c.np.ok else "Run run.bat again")
        self._text(P + 78, y + 17, self._fit(title, 10, True, CW - 196), 10, True)
        self._text(P + 78, y + 39, self._fit(artist, 9, False, CW - 196), 9, color=MUTED)
        bx = W - P - 112
        playing = np.get("playing")
        for j, (nm, ic, val) in enumerate([("prev", "last_track_button", "previous"),
                                           ("play", "pause_button" if playing else "play_button", "toggle"),
                                           ("next", "next_track_button", "next")]):
            self._icon_btn(bx + j * 36, y + 24, 28, icon3d(ic, self.s(28)), nm,
                           lambda v=val: c.run_action({"type": "np", "value": v}), active=(nm == "play" and playing))

        # sliders
        y = 458
        rows = []
        if show_vol:
            rows.append(("vol", "muted_speaker" if c.audio.master_muted() else "speaker_high_volume", "Volume", self._volume()))
        if show_screen:
            rows.append(("scr", "sun", "Screen", (self._screen or 0) / 100 if self._screen is not None else None))
        rows.append(("deck", "light_bulb", "Deck", cfg.get("brightness", 80) / 100))
        for name, ic, lbl, v in rows:
            self._img(P + 2, y + 4, icon3d(ic, self.s(24)))
            tx0, tx1 = P + 40, W - P - 48
            self._slider(name, tx0, y + 9, tx1 - tx0, v)
            self._text(W - P, y + 16, "--" if v is None else f"{round(v * 100)}%", 9, True,
                       TEXT if self.drag == name else MUTED, "e")
            if name == "vol":
                self._hit(P, y, 30, 32, "mute", lambda: c.audio.master_mute_toggle())
            y += 38

        # focus timer
        y += 6
        tm = c.timer
        self._box(P, y, CW, 56, 16, CARD + (255,))
        self._img(P + 12, y + 12, icon3d("timer_clock", self.s(32)))
        mm, ss = divmod(int(tm["remaining"] + 0.99), 60)
        self._text(P + 54, y + 10, "Time's up" if tm["done"] else f"{mm}:{ss:02d}", 14, True, family=FONT)
        state = "Focus timer, running" if tm["running"] else ("Paused" if 0 < tm["remaining"] < tm["total"] else "Focus timer")
        self._text(P + 54, y + 34, state, 8, color=MUTED)
        self._pill(W - P - 150, y + 14, 72, 28, "Pause" if tm["running"] else "Start", "tstart",
                   lambda: c._timer_action("toggle"), primary=not tm["running"])
        self._pill(W - P - 72, y + 14, 62, 28, "Reset", "treset", lambda: c._timer_action("reset"))

        # footer
        y += 74
        self._text(P, y, f"by {library.STUDIO}", 8, True, MUTED, family=FONT)
        if self.startup:
            get, set_ = self.startup
            if self._autostart is None:
                self._autostart = get()
            on = self._autostart
            acc = _hex(self.accent)
            sx = P + 98
            self._box(sx, y - 1, 30, 17, 8, (*acc, 255) if on else (70, 74, 86, 255))
            self._img(sx + (21 if on else 9), y + 7.5, circle(self.s(13), "#ffffff"), "center")
            self._text(sx + 38, y, "Starts with Windows", 8, color=TEXT if self.hover == "auto" else MUTED)

            def flip():
                try:
                    set_(not self._autostart)
                except Exception:
                    pass
                self._autostart = get()
            self._hit(sx - 4, y - 4, 160, 24, "auto", flip)
        self._text(W - P, y, "Quit", 8, True, TEXT if self.hover == "quit" else MUTED, "ne")
        self._hit(W - P - 34, y - 4, 38, 20, "quit", self.quit_app)
        return self.s(W), self.s(H)

    def _slider(self, name, x, y, w, v):
        acc = _hex(self.accent)
        self._box(x, y + 4, w, 6, 3, (52, 56, 66, 255))
        if v is not None:
            fw = max(6, w * max(0.0, min(1.0, v)))
            self._box(x, y + 4, fw, 6, 3, (*acc, 255))
            d = 16 if (self.hover == name or self.drag == name) else 14
            self._img(x + fw, y + 7, circle(self.s(d), "#ffffff"), "center")
        self._hit(x - 8, y - 6, w + 16, 26, name, None, drag=(x, w))

    # ---------------- values ----------------
    def _volume(self):
        t, v = self._vol
        if self.drag != "vol" and time.time() - t > 1.0:
            v = self.core.audio.master(0)
            self._vol = (time.time(), v)
        return v

    def _set_slider(self, name, f):
        f = max(0.0, min(1.0, f))
        c = self.core
        if name == "vol":
            c.audio.set_master(f)
            self._vol = (time.time(), f)
        elif name == "scr":
            self._screen = c.bright.set(round(f * 100))
        elif name == "deck":
            c.set_brightness(round(f * 100))
            if self._save_job:
                self.root.after_cancel(self._save_job)
            self._save_job = self.root.after(600, c.save)

    def _press_key(self, i):
        c = self.core
        k = c.cfg["pages"][c.page_index]["keys"].get(str(i), {})
        threading.Thread(target=c._fire, args=(("key", i), "tap", k.get("action")), daemon=True).start()

    def _studio(self):
        self.hide()
        self.open_studio()

    # ---------------- mouse ----------------
    def _find(self, e):
        for x0, y0, x1, y1, name, cb, drag in reversed(self.hits):
            if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                return name, cb, drag
        return None, None, None

    def _set_hover(self, name):
        if name != self.hover:
            self.hover = name
            self.cv.config(cursor="hand2" if name else "")
            if self.visible and self.drag is None:
                self.draw()

    def _motion(self, e):
        self._set_hover(self._find(e)[0])

    def _down(self, e):
        name, cb, drag = self._find(e)
        if drag:
            self.drag = name
            self._drag_geo = drag
            self._drag(e)
        elif cb:
            self.pressed = name
            self.draw()

            def fire():
                self.pressed = None
                cb()
                if self.visible:
                    self.draw()
            self.root.after(90, fire)

    def _drag(self, e):
        if self.drag:
            x, w = self._drag_geo
            self._set_slider(self.drag, (e.x / self.k - x) / w)
            self.draw()

    def _up(self, e):
        if self.drag:
            self.drag = None
            self.draw()

    def run(self):
        self.root.mainloop()
