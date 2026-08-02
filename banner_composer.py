from PIL import Image, ImageDraw, ImageFont
import io, base64, os

FEED_W = 1080
FEED_H = 1350   # 4:5 Instagram portrait

_BASE = os.path.join(os.path.dirname(__file__), "fonts")
_FONT_CANDIDATES_BOLD = [
    os.path.join(_BASE, "arialbd.ttf"),
    r"C:\Windows\Fonts\arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]
_FONT_CANDIDATES_REG = [
    os.path.join(_BASE, "arial.ttf"),
    r"C:\Windows\Fonts\arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


def _find_font(candidates):
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


F_BOLD = _find_font(_FONT_CANDIDATES_BOLD)
F_REG  = _find_font(_FONT_CANDIDATES_REG)


def _font(path, size):
    try:
        if path:
            return ImageFont.truetype(path, size)
    except Exception:
        pass
    return ImageFont.load_default()


def _wrap(text, font, max_w, draw):
    words = text.split()
    lines, cur = [], []
    for w in words:
        test = " ".join(cur + [w])
        if draw.textbbox((0, 0), test, font=font)[2] > max_w and cur:
            lines.append(" ".join(cur))
            cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(" ".join(cur))
    return lines


def _cover_crop(image_bytes: bytes, w=FEED_W, h=FEED_H) -> Image.Image:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    iw, ih = img.size
    scale = max(w / iw, h / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    img = img.resize((nw, nh), Image.LANCZOS)
    x, y = (nw - w) // 2, (nh - h) // 2
    return img.crop((x, y, x + w, y + h))


def _pill(draw, x, y, text, font, bg=(37, 99, 235), fg=(255, 255, 255)):
    bb = draw.textbbox((0, 0), text, font=font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    px, py = 52, 20
    bw, bh = tw + px * 2, th + py * 2
    draw.rounded_rectangle([x, y, x + bw, y + bh], radius=bh // 2, fill=bg)
    draw.text((x + px, y + py), text, font=font, fill=fg)
    return bh


def _pill_center(draw, W, y, text, font, bg=(37, 99, 235), fg=(255, 255, 255)):
    bb = draw.textbbox((0, 0), text, font=font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    px, py = 52, 20
    bw, bh = tw + px * 2, th + py * 2
    x = (W - bw) // 2
    draw.rounded_rectangle([x, y, x + bw, y + bh], radius=bh // 2, fill=bg)
    draw.text((x + px, y + py), text, font=font, fill=fg)
    return bh


def _gradient_overlay(img: Image.Image, y_start: int, color=(0, 0, 0),
                      alpha_start=0, alpha_end=210) -> Image.Image:
    """Dark gradient overlay from y_start to bottom for text readability."""
    W, H = img.size
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    zone = H - y_start
    if zone <= 0:
        return img
    r, g, b = color
    for dy in range(zone):
        t = dy / zone
        a = int(alpha_start + (alpha_end - alpha_start) * t)
        draw.line([(0, y_start + dy), (W - 1, y_start + dy)], fill=(r, g, b, a))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def _gradient_overlay_top(img: Image.Image, y_end: int, color=(0, 0, 0),
                           alpha_start=190, alpha_end=0) -> Image.Image:
    """Dark gradient from top (fades out downward)."""
    W, H = img.size
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    r, g, b = color
    for y in range(min(y_end, H)):
        t = y / y_end
        a = int(alpha_start + (alpha_end - alpha_start) * t)
        draw.line([(0, y), (W - 1, y)], fill=(r, g, b, a))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def _hex_to_rgb(hex_color: str, fallback=(0, 0, 0)) -> tuple:
    try:
        h = hex_color.lstrip('#')
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
    except Exception:
        return fallback


# ── Style 1: DARK ────────────────────────────────────────────────────────────
# Full-bleed photo · dark gradient bottom half · white text overlay

def style_dark(base: Image.Image, headline: str, bullets: list, cta: str) -> Image.Image:
    W, H = FEED_W, FEED_H

    img = _gradient_overlay(base, int(H * 0.46), color=(3, 7, 18), alpha_start=0, alpha_end=218)
    draw = ImageDraw.Draw(img)

    fh = _font(F_BOLD, 90)
    ft = _font(F_REG,  43)
    fc = _font(F_BOLD, 46)
    margin, tw = 64, W - 128
    y = int(H * 0.535)

    for line in _wrap(headline, fh, tw, draw)[:2]:
        draw.text((margin, y), line, font=fh, fill=(255, 255, 255))
        y += 108

    y += 18
    if bullets:
        draw.text((margin, y), f"✦  {bullets[0]}", font=ft, fill=(148, 196, 255))
        y += 58

    y += 30
    _pill(draw, margin, y, cta, fc, bg=(37, 99, 235))

    return img


# ── Style 2: PREMIUM ─────────────────────────────────────────────────────────
# Blue brand bar top · full photo · dark gradient bottom · centered text

def style_premium(base: Image.Image, headline: str, bullets: list, cta: str) -> Image.Image:
    W, H = FEED_W, FEED_H

    img = _gradient_overlay(base, int(H * 0.42), color=(2, 10, 30), alpha_start=0, alpha_end=228)
    draw = ImageDraw.Draw(img)

    # Blue brand bar at top
    draw.rectangle([0, 0, W, 84], fill=(37, 99, 235))
    fl = _font(F_BOLD, 36)
    draw.text((50, 22), "Adai  ·  Реклама Instagram & Facebook", font=fl, fill=(255, 255, 255))

    fh = _font(F_BOLD, 86)
    ft = _font(F_REG,  41)
    fc = _font(F_BOLD, 44)
    margin, tw = 64, W - 128
    y = int(H * 0.49)

    # Centered headline
    for line in _wrap(headline, fh, tw, draw)[:2]:
        bb = draw.textbbox((0, 0), line, font=fh)
        lw = bb[2] - bb[0]
        draw.text(((W - lw) // 2, y), line, font=fh, fill=(255, 255, 255))
        y += 102

    y += 18
    for b in (bullets or [])[:2]:
        draw.text((margin, y), f"→  {b}", font=ft, fill=(147, 197, 253))
        y += 52

    y += 28
    _pill_center(draw, W, y, cta, fc, bg=(255, 255, 255), fg=(10, 22, 60))

    return img


# ── Style 3: CARD ─────────────────────────────────────────────────────────────
# Photo top 62% · white card panel bottom 38% · dark text

def style_card(base: Image.Image, headline: str, bullets: list, cta: str) -> Image.Image:
    W, H = FEED_W, FEED_H
    PHOTO_H = int(H * 0.615)

    canvas = Image.new("RGB", (W, H), (250, 251, 255))
    canvas.paste(base.crop((0, 0, W, PHOTO_H)), (0, 0))

    draw = ImageDraw.Draw(canvas)
    draw.rectangle([0, PHOTO_H, W, PHOTO_H + 6], fill=(37, 99, 235))

    fh = _font(F_BOLD, 82)
    ft = _font(F_REG,  40)
    fc = _font(F_BOLD, 44)
    margin, tw = 60, W - 120
    y = PHOTO_H + 42

    for line in _wrap(headline, fh, tw, draw)[:2]:
        draw.text((margin, y), line, font=fh, fill=(8, 16, 44))
        y += 96

    y += 14
    if bullets:
        draw.text((margin, y), f"✦  {bullets[0]}", font=ft, fill=(37, 99, 235))
        y += 54

    y += 26
    _pill(draw, margin, y, cta, fc, bg=(37, 99, 235))

    return canvas


# ── AI Creative Director composer ────────────────────────────────────────────
# Layout: dark gradient top (headline) + clear center (product) + dark gradient bottom (bullets+CTA)

_FONT_CANDIDATES_SERIF = [
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    r"C:\Windows\Fonts\georgiabd.ttf",
    r"C:\Windows\Fonts\georgia.ttf",
]
F_SERIF = _find_font(_FONT_CANDIDATES_SERIF)


def _get_fonts(font_style: str):
    """Return (headline_font_path, body_font_path) based on style."""
    if font_style == "elegant_serif":
        return F_SERIF or F_BOLD, F_SERIF or F_REG
    return F_BOLD, F_REG  # bold_sans and modern_display both use bold


def compose_creative_banner(image_bytes: bytes, text_overlay: dict,
                             color_scheme: dict, font_style: str = "bold_sans") -> bytes:
    """
    Compose one banner using the AI Creative Director's structured output.
    Layout: dark top zone (city tag + headline) · clear center (product) · dark bottom zone (bullets + CTA)
    """
    W, H = FEED_W, FEED_H
    base = _cover_crop(image_bytes)

    # Parse colors — only bg and CTA use AI colors; ALL text is white
    bg_color = _hex_to_rgb(color_scheme.get("primary_bg", "#050912"), (5, 9, 18))
    cta_bg   = _hex_to_rgb(color_scheme.get("cta_bg",     "#2563EB"), (37, 99, 235))

    WHITE      = (255, 255, 255)
    WHITE_DIM  = (220, 220, 220)   # subheadline — slightly dimmer white

    # Apply gradients: top 42% fades to transparent, bottom 55% fades to dark
    img = _gradient_overlay_top(base, int(H * 0.42), bg_color, alpha_start=195, alpha_end=0)
    img = _gradient_overlay(img,      int(H * 0.52), bg_color, alpha_start=0,   alpha_end=222)

    draw = ImageDraw.Draw(img)
    fh_path, fb_path = _get_fonts(font_style)

    fh  = _font(fh_path, 88)   # headline
    fsb = _font(fb_path, 40)   # subheadline / bullets
    fc  = _font(fh_path, 44)   # CTA
    fct = _font(fb_path, 28)   # city tag

    margin, tw = 64, W - 128

    # ── City tag (top right) ──────────────────────────────────────────────────
    city = (text_overlay.get("city_tag") or "").strip()
    if city:
        bb = draw.textbbox((0, 0), city, font=fct)
        cw, ch = bb[2] - bb[0], bb[3] - bb[1]
        px, py = 20, 10
        rx = W - cw - px * 2 - 24
        ry = 28
        draw.rounded_rectangle([rx, ry, rx + cw + px * 2, ry + ch + py * 2],
                                radius=8, fill=(*bg_color, 160))
        draw.text((rx + px, ry + py), city, font=fct, fill=WHITE)

    # ── Hook headline (top zone) ──────────────────────────────────────────────
    headline = (text_overlay.get("hook_headline") or "").strip()
    y = 70
    if font_style == "modern_display":
        headline = headline.upper()
    for line in _wrap(headline, fh, tw, draw)[:2]:
        draw.text((margin, y), line, font=fh, fill=WHITE)
        y += 106

    # ── Subheadline ───────────────────────────────────────────────────────────
    sub = (text_overlay.get("subheadline") or "").strip()
    if sub:
        y += 8
        draw.text((margin, y), sub, font=fsb, fill=WHITE_DIM)

    # ── Bullets (bottom zone) ─────────────────────────────────────────────────
    bullets = text_overlay.get("bullets") or []
    y_b = int(H * 0.645)
    for b in bullets[:3]:
        draw.text((margin, y_b), f"— {b}", font=fsb, fill=WHITE)
        y_b += 56

    # ── CTA button (near bottom) ──────────────────────────────────────────────
    cta = (text_overlay.get("cta_button") or "Узнать цену").strip()
    y_cta = int(H * 0.835)
    _pill(draw, margin, y_cta, cta, fc, bg=cta_bg, fg=WHITE)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=94)
    return buf.getvalue()


# ── Direction creative (text-only, no photo) ────────────────────────────────
def generate_creative_for_direction(direction: dict) -> bytes:
    img  = Image.new("RGB", (FEED_W, FEED_H), (6, 12, 28))
    draw = ImageDraw.Draw(img)
    for i in range(FEED_H):
        r = int(6  + (15 - 6)  * i / FEED_H)
        g = int(12 + (25 - 12) * i / FEED_H)
        b = int(28 + (70 - 28) * i / FEED_H)
        draw.line([(0, i), (FEED_W, i)], fill=(r, g, b))
    draw.rectangle([0, 0, FEED_W, 10], fill=(37, 99, 235))

    fh = _font(F_BOLD, 82)
    fb = _font(F_REG,  40)
    fc = _font(F_BOLD, 44)

    name    = direction.get("name", "Реклама")
    utp     = direction.get("utp", "")
    geo     = direction.get("geo", "Казахстан")
    traffic = direction.get("traffic_dest", "whatsapp")
    cta_txt = "Написать в WhatsApp" if traffic == "whatsapp" else "Узнать подробнее"

    y = 80
    for line in _wrap(name, fh, FEED_W - 80, draw)[:3]:
        draw.text((40, y), line, font=fh, fill=(255, 255, 255))
        y += 96
    y += 20
    if utp:
        for line in _wrap(utp, fb, FEED_W - 80, draw)[:3]:
            draw.text((40, y), line, font=fb, fill=(147, 197, 253))
            y += 52
    y += 20
    if geo:
        draw.text((40, y), f"📍 {geo}", font=fb, fill=(100, 160, 255))

    bb  = draw.textbbox((0, 0), cta_txt, font=fc)
    tw2 = bb[2] - bb[0]; th2 = bb[3] - bb[1]
    px, py = 52, 18
    bw, bh = tw2 + px * 2, th2 + py * 2
    bx = (FEED_W - bw) // 2
    by = FEED_H - bh - 90
    draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=bh // 2, fill=(37, 99, 235))
    draw.text((bx + px, by + py), cta_txt, font=fc, fill=(255, 255, 255))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


# ── Public API ────────────────────────────────────────────────────────────────
def create_banners(image_bytes: bytes, headlines: list, bullets: list, cta: str) -> list:
    while len(headlines) < 3:
        headlines.append(headlines[0] if headlines else "Узнайте больше")

    base = _cover_crop(image_bytes)

    variants = [
        ("Dark",    style_dark(base.copy(),    headlines[0], bullets, cta)),
        ("Premium", style_premium(base.copy(), headlines[1], bullets, cta)),
        ("Card",    style_card(base.copy(),    headlines[2], bullets, cta)),
    ]

    result = []
    for label, composed in variants:
        buf = io.BytesIO()
        composed.save(buf, format="JPEG", quality=94)
        b64 = base64.b64encode(buf.getvalue()).decode()
        result.append({
            "label": label,
            "image": f"data:image/jpeg;base64,{b64}",
            "size":  "1080×1350",
        })
    return result
