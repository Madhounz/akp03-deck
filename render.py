"""Draws key faces: big crisp icons, optional label, optional background."""
from __future__ import annotations

import os
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

EMOJI_FONTS = ["seguiemj.ttf", r"C:\Windows\Fonts\seguiemj.ttf", "NotoColorEmoji.ttf"]
TEXT_FONTS = ["segoeuib.ttf", "seguisb.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"]


@lru_cache(maxsize=32)
def _font(size: int):
    for name in TEXT_FONTS:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _trim(img: Image.Image) -> Image.Image:
    """Cut empty transparent borders so the icon really fills the key."""
    box = img.getchannel("A").getbbox()
    return img.crop(box) if box else img


@lru_cache(maxsize=48)
def _load_icon_cached(path: str, mtime: float) -> Image.Image | None:
    try:
        img = Image.open(path)
        if img.format == "ICO":  # pick the biggest size inside the .ico
            sizes = sorted(img.info.get("sizes", [img.size]), key=lambda s: s[0] * s[1])
            img.size = sizes[-1]
        img.load()
        img = _trim(img.convert("RGBA"))
        img.thumbnail((320, 320), Image.LANCZOS)  # keeps memory small even for huge photos
        return img
    except Exception as e:
        print("Icon error:", e)
        return None


def load_icon(path: str) -> Image.Image | None:
    import icons
    path = icons.resolve(path)
    if not path or not os.path.exists(path):
        return None
    return _load_icon_cached(path, os.path.getmtime(path))


@lru_cache(maxsize=6)
def _gif_cached(path: str, mtime: float):
    try:
        im = Image.open(path)
        n = getattr(im, "n_frames", 1)
        if n < 2:
            return None
        frames = []
        for i in range(min(n, 80)):
            im.seek(i)
            fr = _trim(im.convert("RGBA"))
            fr.thumbnail((200, 200), Image.LANCZOS)
            frames.append((fr, max(40, im.info.get("duration", 100))))
        return frames
    except Exception:
        return None


def gif_frames(path: str):
    """Frames of an animated GIF/WebP icon, or None if it isn't animated."""
    import icons
    path = icons.resolve(path)
    if not path or not path.lower().endswith((".gif", ".webp")) or not os.path.exists(path):
        return None
    return _gif_cached(path, os.path.getmtime(path))


def gif_frame_at(path: str, t: float):
    frames = gif_frames(path)
    if not frames:
        return None
    total = sum(d for _, d in frames)
    ms = (t * 1000) % total
    for img, d in frames:
        if ms < d:
            return img
        ms -= d
    return frames[-1][0]


def emoji_image(ch: str) -> Image.Image | None:
    """3D icon for an emoji when available, else the Windows emoji font."""
    if not ch or not ch.strip():
        return None
    import icons
    f = icons.emoji_file(ch)
    if f:
        img = load_icon(f)
        if img is not None:
            return img
    return _emoji_font_image(ch)


@lru_cache(maxsize=48)
def _emoji_font_image(ch: str) -> Image.Image | None:
    for name in EMOJI_FONTS:
        for size in (200, 136, 109):  # color bitmap fonts only allow fixed sizes
            try:
                font = ImageFont.truetype(name, size)
                canvas = Image.new("RGBA", (size * 3, size * 2), (0, 0, 0, 0))
                ImageDraw.Draw(canvas).text((size // 2, size // 4), ch.strip(), font=font, embedded_color=True)
                if canvas.getchannel("A").getbbox():
                    return _trim(canvas)
            except Exception:
                continue
    return None


def _hex(c: str, fallback=(30, 30, 30)):
    try:
        c = c.lstrip("#")
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return fallback


def _background(k: dict, size: int, wall_tile=None) -> Image.Image:
    mode = k.get("bg", "none")
    if mode == "none" and wall_tile is not None:
        return wall_tile.resize((size, size), Image.LANCZOS) if wall_tile.size != (size, size) else wall_tile.copy()
    if mode == "solid":
        return Image.new("RGB", (size, size), _hex(k.get("color", "#222222")))
    if mode == "gradient":
        r, g, b = _hex(k.get("color", "#7c5cff"))
        top = tuple(min(255, int(v * 1.25 + 25)) for v in (r, g, b))
        bot = tuple(int(v * 0.35) for v in (r, g, b))
        grad = Image.new("RGB", (1, size))
        for y in range(size):
            t = y / max(1, size - 1)
            grad.putpixel((0, y), tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)))
        return grad.resize((size, size))
    return Image.new("RGB", (size, size), (0, 0, 0))  # "none" = black LCD


def render_key(k: dict, size: int = 60, device: bool = False, wall_tile=None, mon=None, accent="#7c5cff",
               t: float | None = None, badge=None) -> Image.Image:
    if k.get("live") and mon is not None:
        img = render_live(k["live"], mon, size, accent, wall_tile if k.get("bg", "none") == "none" else None, t=t)
        return draw_badge(img, badge) if badge else img
    img = _background(k, size, wall_tile)
    icon = None
    if t is not None and k.get("icon"):
        icon = gif_frame_at(k["icon"], t)
    icon = icon or load_icon(k.get("icon", "")) or emoji_image(k.get("emoji", ""))
    label = (k.get("label") or "").strip()
    show_label = bool(label) and (k.get("show_label", True) or icon is None)
    scale = float(k.get("icon_scale", 0.9))

    if icon is not None:
        area = size * scale * (0.70 if show_label else 1.0)
        fitted = ImageOps.contain(icon, (max(1, int(area)), max(1, int(area))), Image.LANCZOS)
        if device:
            fitted = fitted.filter(ImageFilter.UnsharpMask(radius=0.6, percent=60, threshold=2))
        x = (size - fitted.width) // 2
        y = (size - fitted.height) // 2 - (int(size * 0.11) if show_label else 0)
        img.paste(fitted, (x, y), fitted)

    if show_label:
        draw = ImageDraw.Draw(img)
        fs = int(size * (0.17 if icon is not None else 0.24))
        font = _font(fs)
        while draw.textlength(label, font=font) > size * 0.94 and fs > 7:
            fs -= 1
            font = _font(fs)
        w = draw.textlength(label, font=font)
        y = size - fs - int(size * 0.07) if icon is not None else (size - fs) // 2 - int(size * 0.04)
        draw.text(((size - w) / 2, y), label, font=font, fill=(255, 255, 255),
                  stroke_width=max(1, size // 50), stroke_fill=(0, 0, 0))
    return draw_badge(img, badge) if badge else img


def draw_badge(img: Image.Image, badge) -> Image.Image:
    """Red counter (unread mail) or a muted-mic mark in the top right corner."""
    size = img.width
    d = ImageDraw.Draw(img)
    if isinstance(badge, dict) and badge.get("muted"):
        r = size * 0.17
        cx, cy = size - r - size * 0.04, r + size * 0.04
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(239, 68, 68), outline=(0, 0, 0), width=max(1, size // 40))
        d.line((cx - r * 0.5, cy + r * 0.5, cx + r * 0.5, cy - r * 0.5), fill="white", width=max(2, size // 22))
        return img
    n = badge.get("count", 0) if isinstance(badge, dict) else int(badge or 0)
    if n <= 0:
        return img
    text = "99+" if n > 99 else str(n)
    fs = int(size * 0.2)
    font = _font(fs)
    w = max(d.textlength(text, font=font) + size * 0.12, size * 0.3)
    h = size * 0.3
    x1, y0 = size - size * 0.03, size * 0.03
    d.rounded_rectangle((x1 - w, y0, x1, y0 + h), radius=h / 2, fill=(239, 68, 68), outline=(0, 0, 0), width=max(1, size // 40))
    d.text((x1 - w / 2 - d.textlength(text, font=font) / 2, y0 + (h - fs) / 2 - size * 0.02), text, font=font, fill="white")
    return img


def app_icon(size: int = 64) -> Image.Image:
    """Logo for the window and tray: purple tile with a 3x2 key grid."""
    s = size * 4
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=s // 5, fill=(124, 92, 255))
    pad, gap = s * 0.18, s * 0.06
    cw = (s - 2 * pad - 2 * gap) / 3
    ch = (s * 0.5 - gap) / 2
    for r in range(2):
        for c in range(3):
            x0 = pad + c * (cw + gap)
            y0 = s * 0.2 + r * (ch + gap)
            d.rounded_rectangle((x0, y0, x0 + cw, y0 + ch), radius=s // 30, fill=(255, 255, 255, 235))
    for c in range(3):
        cx = pad + c * (cw + gap) + cw / 2
        d.ellipse((cx - cw * 0.32, s * 0.76, cx + cw * 0.32, s * 0.76 + cw * 0.64), fill=(20, 16, 40))
    return img.resize((size, size), Image.LANCZOS)


def _gap_text(d, text, W, S, row, max_scale, fill="white"):
    """Write text across the 3 keys of a row without letters falling into the gaps between keys."""
    pad = S * 0.07
    fs = int(S * max_scale)
    while True:
        font = _font(fs)
        widths = [d.textlength(ch, font=font) for ch in text]
        track = fs * 0.04

        def layout(off):
            xs, x = [], off
            for ch, w in zip(text, widths):
                for b in (S, 2 * S):
                    if ch != " " and x < b + pad and x + w > b - pad:
                        x = b + pad
                xs.append(x)
                x += w + track
            return xs, x - track

        off = (W - sum(widths)) / 2
        for _ in range(8):
            xs, end = layout(off)
            off += ((W - end) - xs[0]) / 2
        xs, end = layout(off)
        if (xs[0] >= pad * 0.6 and end <= W - pad * 0.6) or fs <= 18:
            break
        fs -= 4
    y = row * S + (S - fs) / 2 - S * 0.06
    for ch, x in zip(text, xs):
        d.text((x, y), ch, font=font, fill=fill, stroke_width=max(2, fs // 16), stroke_fill=(0, 0, 0))


# ---------------- pages: wallpaper + splash ----------------

@lru_cache(maxsize=16)
def _wall_cached(path: str, mtime: float, size: int, dim: float):
    try:
        img = Image.open(path).convert("RGB")
    except Exception as e:
        print("Wallpaper error:", e)
        return None
    img = ImageOps.fit(img, (size * 3, size * 2), Image.LANCZOS)
    if dim:
        img = Image.blend(img, Image.new("RGB", img.size, (0, 0, 0)), dim)
    return [img.crop(((i % 3) * size, (i // 3) * size, (i % 3 + 1) * size, (i // 3 + 1) * size)) for i in range(6)]


def wallpaper_tiles(path: str, size: int, dim: float = 0.25):
    """One picture spread across all 6 keys (3 x 2)."""
    if not path or not os.path.exists(path):
        return None
    return _wall_cached(path, os.path.getmtime(path), size, dim)


def splash_tiles(page: dict, index: int, total: int, size: int = 60) -> list[Image.Image]:
    """A banner across the 6 keys shown for a moment when the page changes."""
    S = 240  # draw big, then shrink each tile for sharpness
    W, H = S * 3, S * 2
    bg = _glow_bg(W, H, page.get("accent", "#7c5cff"), page.get("rgb", False))
    d = ImageDraw.Draw(bg)

    # top middle: big emoji
    em = emoji_image(page.get("emoji", ""))
    if em is not None:
        em = ImageOps.contain(em, (int(S * 0.78), int(S * 0.78)), Image.LANCZOS)
        bg.paste(em, (S + (S - em.width) // 2, (S - em.height) // 2), em)

    # top left: page number
    f_big, f_small = _font(int(S * 0.55)), _font(int(S * 0.16))
    num = str(index + 1)
    w = d.textlength(num, font=f_big)
    d.text(((S - w) / 2, S * 0.12), num, font=f_big, fill="white")
    sub = f"of {total}"
    w = d.textlength(sub, font=f_small)
    d.text(((S - w) / 2, S * 0.72), sub, font=f_small, fill=(230, 230, 240))

    # top right: page dots
    n = max(1, total)
    dot, gap = S * 0.09, S * 0.06
    tw = n * dot + (n - 1) * gap
    if tw > S * 0.85:
        dot = gap = S * 0.85 / (2 * n - 1)
        tw = S * 0.85
    x0 = 2 * S + (S - tw) / 2
    for i in range(n):
        x = x0 + i * (dot + gap)
        fill = "white" if i == index else (255, 255, 255, 90)
        d.ellipse((x, S / 2 - dot / 2, x + dot, S / 2 + dot / 2), fill=fill if i == index else (90, 90, 100))

    # bottom row: page name across all 3 keys, never cut by the gaps
    _gap_text(d, (page.get("name") or f"Page {index + 1}").upper(), W, S, 1, 0.5)

    return [bg.crop(((i % 3) * S, (i // 3) * S, (i % 3 + 1) * S, (i // 3 + 1) * S)).resize((size, size), Image.LANCZOS)
            for i in range(6)]


def _rainbow(W, H):
    import colorsys
    line = Image.new("RGB", (W, 1))
    for x in range(W):
        r, g, b = colorsys.hsv_to_rgb(x / W * 0.85, 0.85, 1.0)
        line.putpixel((x, 0), (int(r * 255), int(g * 255), int(b * 255)))
    return line.resize((W, H))


def _glow_bg(W, H, accent, rgb=False):
    r, g, b = _hex(accent, (124, 92, 255))
    base = Image.new("RGB", (W, H), (8, 8, 10) if rgb else (int(r * 0.12), int(g * 0.12), int(b * 0.12)))
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse((W * 0.1, -H * 0.35, W * 0.9, H * 0.85), fill=255)
    glow = glow.filter(ImageFilter.GaussianBlur(min(W, H) * 0.22))
    color = _rainbow(W, H) if rgb else Image.new("RGB", (W, H), (r, g, b))
    return Image.composite(color, base, glow)


def _tile_text(d, text, col, row, S, scale, fill="white", dy=0.0):
    fs = int(S * scale)
    font = _font(fs)
    while d.textlength(text, font=font) > S * 0.86 and fs > 14:
        fs -= 2
        font = _font(fs)
    w = d.textlength(text, font=font)
    d.text((col * S + (S - w) / 2, row * S + (S - fs) / 2 - S * 0.05 + dy * S), text, font=font, fill=fill,
           stroke_width=max(2, fs // 16), stroke_fill=(0, 0, 0))


def credit_tiles(author: str, studio: str, size: int = 60) -> list[Image.Image]:
    """Credits banner shown on the deck when it connects. One word per key."""
    S = 240
    W, H = S * 3, S * 2
    bg = _glow_bg(W, H, "#7c5cff", rgb=True)
    d = ImageDraw.Draw(bg)
    logo = app_icon(int(S * 0.7))
    bg.paste(logo, (int((S - logo.width) / 2), int((S - logo.height) / 2)), logo)
    _tile_text(d, "AKP03", 1, 0, S, 0.34)
    _tile_text(d, "DECK", 2, 0, S, 0.36)
    _tile_text(d, "made by", 0, 1, S, 0.2, (235, 235, 245))
    _tile_text(d, author, 1, 1, S, 0.3)
    _tile_text(d, studio.upper(), 2, 1, S, 0.22)
    return [bg.crop(((i % 3) * S, (i // 3) * S, (i % 3 + 1) * S, (i // 3 + 1) * S)).resize((size, size), Image.LANCZOS)
            for i in range(6)]


# ---------------- live tiles ----------------
_HOT = [(45, 212, 191), (250, 204, 21), (244, 63, 94)]


def _hot(t: float):
    t = max(0.0, min(1.0, t))
    a, b, u = (_HOT[0], _HOT[1], t * 2) if t < 0.5 else (_HOT[1], _HOT[2], (t - 0.5) * 2)
    return tuple(int(a[i] + (b[i] - a[i]) * u) for i in range(3))


def _center_text(d, text, font, cx, y, fill):
    w = d.textlength(text, font=font)
    d.text((cx - w / 2, y), text, font=font, fill=fill)


def render_live(kind: str, mon, size: int, accent: str = "#7c5cff", wall_tile=None, t=None) -> Image.Image:
    import time as _t
    S = 240
    info0 = mon.get(kind)
    if info0.get("style") in ("np", "timer", "mic"):
        return _render_special(info0, size, accent, _t.time() if t is None else t)
    if wall_tile is not None:
        img = Image.blend(wall_tile.resize((S, S)), Image.new("RGB", (S, S), (0, 0, 0)), 0.55)
    else:
        img = Image.new("RGB", (S, S), (0, 0, 0))
    d = ImageDraw.Draw(img)
    info = mon.get(kind)
    muted = (150, 156, 172)
    ar, ag, ab = _hex(accent, (124, 92, 255))

    if info["style"] == "clock":
        now = _t.localtime()
        sec = now.tm_sec + (_t.time() % 1)
        d.arc((14, 14, S - 14, S - 14), 0, 360, fill=(30, 32, 40), width=8)
        d.arc((14, 14, S - 14, S - 14), -90, -90 + 360 * sec / 60, fill=(ar, ag, ab), width=8)
        f = _font(int(S * 0.25))
        _center_text(d, _t.strftime("%H:%M", now), f, S / 2, S * 0.32, (255, 255, 255))
        _center_text(d, _t.strftime("%a %d", now).upper(), _font(int(S * 0.13)), S / 2, S * 0.64, muted)
        return img.resize((size, size), Image.LANCZOS)

    if info["style"] == "spark":
        hist = info.get("hist") or [0]
        top = max(max(hist), 1)
        x0, x1, y0, y1 = 10, S - 10, S * 0.52, S - 14
        n = max(2, len(hist))
        pts = [(x0 + (x1 - x0) * i / (n - 1), y1 - (y1 - y0) * (hist[i] / top if i < len(hist) else 0)) for i in range(n)]
        area = Image.new("L", (S, S), 0)
        ImageDraw.Draw(area).polygon([(x0, y1)] + pts + [(x1, y1)], fill=120)
        img.paste(Image.new("RGB", (S, S), (ar, ag, ab)), (0, 0), area)
        d.line(pts, fill=(min(255, ar + 80), min(255, ag + 80), min(255, ab + 80)), width=5, joint="curve")
        arrow = "↓" if kind == "net_down" else "↑"
        f = _font(int(S * 0.27))
        _center_text(d, info["text"], f, S / 2, S * 0.08, (255, 255, 255))
        _center_text(d, f"{arrow} {info['unit']}", _font(int(S * 0.13)), S / 2, S * 0.37, muted)
        return img.resize((size, size), Image.LANCZOS)

    # ring gauge
    box, width, start, sweep = (16, 16, S - 16, S - 16), 20, 135, 270
    d.arc(box, start, start + sweep, fill=(34, 36, 44), width=width)
    frac = info.get("frac", 0)
    steps = int(sweep * frac / 3)
    for j in range(steps):
        a0 = start + j * 3
        d.arc(box, a0, min(a0 + 3.8, start + sweep * frac), fill=_hot(j * 3 / sweep), width=width)
    color = (90, 94, 108) if info.get("missing") else (255, 255, 255)
    text, unit = info.get("text", "--"), info.get("unit", "")
    fs = int(S * 0.36)
    f, fu = _font(fs), _font(int(S * 0.15))
    while d.textlength(text, font=f) > S * 0.56 and fs > 30:
        fs -= 4
        f = _font(fs)
    tw, uw = d.textlength(text, font=f), (d.textlength(unit, font=fu) if not info.get("missing") else 0)
    x = (S - tw - uw) / 2
    y = S * 0.48 - fs * 0.62
    d.text((x, y), text, font=f, fill=color)
    if uw:
        d.text((x + tw + 2, y + fs * 0.12), unit, font=fu, fill=_hot(frac))
    label = info["label"] if not info.get("missing") else f"{info['label']} N/A"
    _center_text(d, info.get("sub") or label, _font(int(S * 0.14)), S / 2, S * 0.72, muted)
    return img.resize((size, size), Image.LANCZOS)


# ---------------- special live tiles ----------------

def _icon3d(name: str):
    import icons
    return load_icon(icons.p3d(name))


def _render_special(info: dict, size: int, accent: str, t: float) -> Image.Image:
    import math
    S = 240
    ar, ag, ab = _hex(accent, (124, 92, 255))
    img = Image.new("RGB", (S, S), (0, 0, 0))
    d = ImageDraw.Draw(img)
    st = info["style"]

    if st == "np":  # now playing: full bleed album art
        art = info.get("art")
        if art is not None:
            img = ImageOps.fit(art.convert("RGB"), (S, S), Image.LANCZOS)
            if not info.get("playing"):
                img = Image.blend(img, Image.new("RGB", (S, S), (0, 0, 0)), 0.55)
        else:
            ic = _icon3d("musical_note")
            if ic is not None:
                ic = ImageOps.contain(ic, (int(S * 0.62), int(S * 0.62)), Image.LANCZOS)
                img.paste(ic, ((S - ic.width) // 2, int(S * 0.1)), ic)
        d = ImageDraw.Draw(img)
        if not info.get("title"):
            _center_text(d, "NOTHING PLAYING" if art is None else "", _font(int(S * 0.11)), S / 2, S * 0.8, (150, 156, 172))
        elif info.get("playing"):  # little equalizer, bottom right
            bw, gap, base = S * 0.05, S * 0.025, S * 0.93
            x0 = S - 4 * bw - 3 * gap - S * 0.07
            sh = Image.new("L", (S, S), 0)
            ImageDraw.Draw(sh).rounded_rectangle((x0 - S * 0.04, S * 0.62, S - S * 0.03, S * 0.97), radius=S * 0.05, fill=150)
            img.paste((0, 0, 0), (0, 0), sh)
            for i in range(4):
                h = S * (0.1 + 0.16 * (0.5 + 0.5 * math.sin(t * (6 + i * 1.7) + i * 1.3)))
                x = x0 + i * (bw + gap)
                d.rounded_rectangle((x, base - h, x + bw, base), radius=bw / 2, fill=(ar, ag, ab))
        else:
            r = S * 0.17
            d.ellipse((S / 2 - r * 1.6, S / 2 - r * 1.6, S / 2 + r * 1.6, S / 2 + r * 1.6), fill=(0, 0, 0))
            d.rounded_rectangle((S / 2 - r * 0.75, S / 2 - r, S / 2 - r * 0.2, S / 2 + r), radius=6, fill="white")
            d.rounded_rectangle((S / 2 + r * 0.2, S / 2 - r, S / 2 + r * 0.75, S / 2 + r), radius=6, fill="white")
        return img.resize((size, size), Image.LANCZOS)

    if st == "timer":
        rem, total = info.get("remaining", 0), max(1, info.get("total", 1))
        frac = max(0.0, min(1.0, rem / total))
        done = info.get("done")
        col = (244, 63, 94) if (rem <= 60 and info.get("running")) or done else (ar, ag, ab)
        if done and int(t * 3) % 2:
            img.paste((90, 16, 30), (0, 0, S, S))
            d = ImageDraw.Draw(img)
        box = (14, 14, S - 14, S - 14)
        d.arc(box, 0, 360, fill=(34, 36, 44), width=16)
        if frac > 0:
            d.arc(box, -90, -90 + 360 * frac, fill=col, width=16)
        m, s_ = divmod(int(math.ceil(rem)), 60)
        _center_text(d, "DONE" if done else f"{m}:{s_:02d}", _font(int(S * (0.24 if done else 0.27))), S / 2, S * 0.33, (255, 255, 255))
        state = "TAP" if done else ("FOCUS" if info.get("running") else "PAUSED" if rem < total else "START")
        _center_text(d, state, _font(int(S * 0.12)), S / 2, S * 0.64, (150, 156, 172) if not info.get("running") else col)
        return img.resize((size, size), Image.LANCZOS)

    if st == "mic":
        muted = info.get("muted")
        col = (120, 124, 136) if muted is None else ((239, 68, 68) if muted else (61, 220, 132))
        glow = Image.new("L", (S, S), 0)
        ImageDraw.Draw(glow).ellipse((S * 0.12, S * 0.08, S * 0.88, S * 0.84), fill=110)
        glow = glow.filter(ImageFilter.GaussianBlur(S * 0.12))
        img.paste(col, (0, 0), glow)
        ic = _icon3d("studio_microphone")
        if ic is not None:
            ic = ImageOps.contain(ic, (int(S * 0.58), int(S * 0.58)), Image.LANCZOS)
            if muted:
                ic = Image.blend(ic, Image.new("RGBA", ic.size, (0, 0, 0, 0)), 0.0)
            img.paste(ic, ((S - ic.width) // 2, int(S * 0.1)), ic)
        d = ImageDraw.Draw(img)
        if muted:
            d.line((S * 0.22, S * 0.72, S * 0.78, S * 0.12), fill=(0, 0, 0), width=26)
            d.line((S * 0.22, S * 0.72, S * 0.78, S * 0.12), fill=(239, 68, 68), width=14)
        _center_text(d, "MUTED" if muted else ("LIVE" if muted is False else "MIC"), _font(int(S * 0.15)), S / 2, S * 0.76, col)
        return img.resize((size, size), Image.LANCZOS)
    return img.resize((size, size))


# ---------------- overlays: AI busy, messages, dice, coin ----------------

def overlay_tile(kind: str, t: float, accent: str = "#7c5cff", text: str = "", value=None, size: int = 60) -> Image.Image:
    import math
    S = 240
    ar, ag, ab = _hex(accent, (124, 92, 255))
    img = Image.new("RGB", (S, S), (0, 0, 0))
    d = ImageDraw.Draw(img)
    if kind == "spin":  # thinking: sparkles with an orbiting light
        ic = _icon3d("sparkles")
        if ic is not None:
            k = 0.5 + 0.08 * math.sin(t * 6)
            ic = ImageOps.contain(ic, (int(S * k), int(S * k)), Image.LANCZOS)
            img.paste(ic, ((S - ic.width) // 2, (S - ic.height) // 2), ic)
        a = (t * 360 * 1.2) % 360
        for i in range(10):
            col = tuple(int(c * (1 - i / 10)) for c in (ar, ag, ab))
            d.arc((14, 14, S - 14, S - 14), a - i * 12 - 12, a - i * 12, fill=col, width=14)
    elif kind == "ok":
        ic = _icon3d("check_mark_button")
        if ic is not None:
            ic = ImageOps.contain(ic, (int(S * 0.62), int(S * 0.62)), Image.LANCZOS)
            img.paste(ic, ((S - ic.width) // 2, int(S * 0.08)), ic)
        _center_text(d, text or "DONE", _font(int(S * 0.15)), S / 2, S * 0.74, (61, 220, 132))
    elif kind == "msg":
        img.paste((int(ar * .25), int(ag * .25), int(ab * .25)), (0, 0, S, S))
        lines = (text or "").split("\n")
        fs = int(S * (0.2 if len(lines) > 1 else 0.24))
        y = (S - len(lines) * fs * 1.15) / 2
        for ln in lines:
            f = _font(fs)
            while d.textlength(ln, font=f) > S * 0.9 and fs > 16:
                fs -= 2
                f = _font(fs)
            _center_text(d, ln, f, S / 2, y, (255, 255, 255))
            y += fs * 1.15
    elif kind == "dice":
        n = value or 1
        pad = S * 0.14
        d.rounded_rectangle((pad, pad, S - pad, S - pad), radius=S * 0.12, fill=(245, 245, 250))
        pos = {1: [(1, 1)], 2: [(0, 0), (2, 2)], 3: [(0, 0), (1, 1), (2, 2)], 4: [(0, 0), (2, 0), (0, 2), (2, 2)],
               5: [(0, 0), (2, 0), (1, 1), (0, 2), (2, 2)], 6: [(0, 0), (2, 0), (0, 1), (2, 1), (0, 2), (2, 2)]}[n]
        cell = (S - 2 * pad) / 3
        for cx, cy in pos:
            x, y, r = pad + cell * (cx + 0.5), pad + cell * (cy + 0.5), S * 0.07
            d.ellipse((x - r, y - r, x + r, y + r), fill=(239, 68, 68) if n == 1 else (24, 24, 30))
    elif kind == "coin":
        ic = _icon3d("coin")
        squash = abs(math.cos(t * 9)) if value is None else 1.0
        if ic is not None:
            w = max(4, int(S * 0.62 * squash))
            ic = ic.resize((w, int(S * 0.62)), Image.LANCZOS)
            img.paste(ic, ((S - w) // 2, int(S * 0.08)), ic)
        if value:
            _center_text(d, value, _font(int(S * 0.15)), S / 2, S * 0.76, (250, 204, 21))
    return img.resize((size, size), Image.LANCZOS)


def solid_glow(color, lit: bool, size: int = 60, label: str = "") -> Image.Image:
    """Simon game pads."""
    S = 120
    r, g, b = color
    img = Image.new("RGB", (S, S), (0, 0, 0))
    if lit:
        img = _glow_bg(S, S, "#%02x%02x%02x" % color)
        ImageDraw.Draw(img).rounded_rectangle((10, 10, S - 10, S - 10), radius=18, fill=(min(255, r + 60), min(255, g + 60), min(255, b + 60)))
    else:
        ImageDraw.Draw(img).rounded_rectangle((10, 10, S - 10, S - 10), radius=18, fill=(r // 5, g // 5, b // 5),
                                                outline=(r // 2, g // 2, b // 2), width=3)
    if label:
        _center_text(ImageDraw.Draw(img), label, _font(int(S * 0.2)), S / 2, S * 0.4, "white")
    return img.resize((size, size), Image.LANCZOS)


def rainbow_tile(i: int, t: float, size: int = 60) -> Image.Image:
    import colorsys, math
    S = 60
    img = Image.new("RGB", (S, S))
    px = img.load()
    col, row = i % 3, i // 3
    for y in range(0, S, 2):
        for x in range(0, S, 2):
            gx, gy = col * 1.25 + x / S, row * 1.25 + y / S
            h = (gx * 0.18 + gy * 0.1 - t * 0.35) % 1.0
            v = 0.55 + 0.45 * math.sin(t * 4 + gx * 3 + gy * 2)
            r, g, b = colorsys.hsv_to_rgb(h, 0.9, v)
            c = (int(r * 255), int(g * 255), int(b * 255))
            px[x, y] = px[x + 1, y] = px[x, y + 1] = px[x + 1, y + 1] = c
    return img.resize((size, size)) if size != S else img


def banner(lines, accent="#7c5cff", rgb=False, size: int = 60) -> list[Image.Image]:
    """Generic 3 x 2 banner: lines = [(text, row, scale)]."""
    S = 240
    W, H = S * 3, S * 2
    bg = _glow_bg(W, H, accent, rgb)
    d = ImageDraw.Draw(bg)
    for text, row, scale in lines:
        _gap_text(d, text.upper(), W, S, row, scale)
    return [bg.crop(((i % 3) * S, (i // 3) * S, (i % 3 + 1) * S, (i // 3 + 1) * S)).resize((size, size), Image.LANCZOS)
            for i in range(6)]


def hud_tiles(icon, title: str, frac, text: str, accent="#7c5cff", size: int = 60) -> list[Image.Image]:
    """Knob dashboard on the bottom row: icon | title + bar | value + bar."""
    S = 240
    ar, ag, ab = _hex(accent, (124, 92, 255))
    tiles = []
    a = _glow_bg(S, S, accent)
    if icon is not None:
        ic = ImageOps.contain(icon, (int(S * 0.7), int(S * 0.7)), Image.LANCZOS)
        a.paste(ic, ((S - ic.width) // 2, (S - ic.height) // 2), ic)
    tiles.append(a)
    pad, by, bh = S * 0.1, S * 0.66, S * 0.16
    seg = S - 2 * pad
    for j in range(2):
        t_ = Image.new("RGB", (S, S), (0, 0, 0))
        d = ImageDraw.Draw(t_)
        if frac is not None:
            d.rounded_rectangle((pad, by, S - pad, by + bh), radius=bh / 2, fill=(34, 36, 44))
            f = max(0.0, min(1.0, frac * 2 - j))
            if f > 0:
                d.rounded_rectangle((pad, by, pad + max(bh, seg * f), by + bh), radius=bh / 2, fill=(ar, ag, ab))
        label = title.upper() if j == 0 else text
        fs = int(S * (0.2 if j == 0 else 0.34))
        f2 = _font(fs)
        while d.textlength(label, font=f2) > S * 0.88 and fs > 16:
            fs -= 2
            f2 = _font(fs)
        _center_text(d, label, f2, S / 2, (S * 0.3 if frac is not None else S * 0.4) - fs / 2, (255, 255, 255) if j else (200, 205, 220))
        tiles.append(t_)
    return [x.resize((size, size), Image.LANCZOS) for x in tiles]
