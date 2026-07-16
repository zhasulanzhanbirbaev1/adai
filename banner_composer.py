from PIL import Image, ImageDraw, ImageFont
import io, base64, os, sys

SIZE = 1080

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
    for path in candidates:
        if os.path.exists(path):
            return path
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
        test = ' '.join(cur + [w])
        if draw.textbbox((0, 0), test, font=font)[2] > max_w and cur:
            lines.append(' '.join(cur))
            cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(' '.join(cur))
    return lines


def _cta_btn(draw, x, y, text, font):
    w = draw.textbbox((0, 0), text, font=font)[2] + 72
    draw.rounded_rectangle([x, y, x + w, y + 58], radius=29, fill=(59, 130, 246))
    draw.text((x + 36, y + 12), text, font=font, fill=(255, 255, 255))


def _prepare(image_bytes: bytes) -> Image.Image:
    img  = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    w, h = img.size
    side = min(w, h)
    img  = img.crop(((w-side)//2, (h-side)//2, (w+side)//2, (h+side)//2))
    return img.resize((SIZE, SIZE), Image.LANCZOS)


def _gradient(img, from_bottom=True, strength=238):
    overlay = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    zone = int(SIZE * 0.52)
    for i in range(zone):
        a = int(strength * i / zone)
        if from_bottom:
            d.line([(0, SIZE-zone+i), (SIZE, SIZE-zone+i)], fill=(6, 12, 28, a))
        else:
            d.line([(0, zone-i-1), (SIZE, zone-i-1)], fill=(6, 12, 28, a))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


# ── Стиль 1: текст снизу ─────────────────────────────────────────────────────

def style_bottom(img, headline, bullets, cta):
    img  = _gradient(img, from_bottom=True)
    draw = ImageDraw.Draw(img)
    fh, fb, fc = _font(F_BOLD, 68), _font(F_REG, 37), _font(F_BOLD, 39)
    y = int(SIZE * 0.50) + 10
    for line in _wrap(headline, fh, SIZE - 80, draw)[:2]:
        draw.text((40, y), line, font=fh, fill=(255, 255, 255))
        y += 80
    y += 6
    for b in bullets[:3]:
        draw.text((40, y), f"• {b}", font=fb, fill=(185, 215, 255))
        y += 46
    y += 10
    _cta_btn(draw, 40, y, cta, fc)
    return img


# ── Стиль 2: синяя полоска + текст снизу ─────────────────────────────────────

def style_accent(img, headline, bullets, cta):
    img  = _gradient(img, from_bottom=True)
    ov   = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(ov).rectangle([0, 0, SIZE, 80], fill=(59, 130, 246, 230))
    img  = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
    draw = ImageDraw.Draw(img)
    fa, fh, fb, fc = _font(F_BOLD, 34), _font(F_BOLD, 68), _font(F_REG, 37), _font(F_BOLD, 39)
    draw.text((44, 22), bullets[0] if bullets else "", font=fa, fill=(255, 255, 255))
    y = int(SIZE * 0.50) + 10
    for line in _wrap(headline, fh, SIZE - 80, draw)[:2]:
        draw.text((40, y), line, font=fh, fill=(255, 255, 255))
        y += 80
    y += 6
    for b in bullets[1:3]:
        draw.text((40, y), f"✓  {b}", font=fb, fill=(185, 215, 255))
        y += 46
    y += 10
    _cta_btn(draw, 40, y, cta, fc)
    return img


# ── Стиль 3: текст сверху ─────────────────────────────────────────────────────

def style_top(img, headline, bullets, cta):
    img  = _gradient(img, from_bottom=False)
    draw = ImageDraw.Draw(img)
    fh, fb, fc = _font(F_BOLD, 68), _font(F_REG, 37), _font(F_BOLD, 39)
    y = 30
    for line in _wrap(headline, fh, SIZE - 80, draw)[:2]:
        draw.text((40, y), line, font=fh, fill=(255, 255, 255))
        y += 80
    y += 6
    for b in bullets[:3]:
        draw.text((40, y), f"• {b}", font=fb, fill=(185, 215, 255))
        y += 46
    y += 10
    _cta_btn(draw, 40, y, cta, fc)
    return img


# ── Генератор баннера из бриф направления (без фото) ─────────────────────────

def generate_creative_for_direction(direction: dict) -> bytes:
    """Create a styled text-only banner from direction brief. Returns JPEG bytes."""
    img = Image.new("RGB", (SIZE, SIZE), (6, 12, 28))
    draw = ImageDraw.Draw(img)

    # blue→dark gradient
    for i in range(SIZE):
        r = int(6 + (20 - 6) * i / SIZE)
        g = int(12 + (30 - 12) * i / SIZE)
        b = int(28 + (80 - 28) * i / SIZE)
        draw.line([(0, i), (SIZE, i)], fill=(r, g, b))

    # top accent bar
    draw.rectangle([0, 0, SIZE, 12], fill=(59, 130, 246))

    fh = _font(F_BOLD, 64)
    fb_f = _font(F_REG, 36)
    fc = _font(F_BOLD, 38)

    name = direction.get("name", "Реклама")
    utp = direction.get("utp", "")
    geo = direction.get("geo", "Казахстан")
    traffic = direction.get("traffic_dest", "whatsapp")
    cta_text = "Написать в WhatsApp" if traffic == "whatsapp" else "Узнать подробнее"

    y = 60
    for line in _wrap(name, fh, SIZE - 80, draw)[:3]:
        draw.text((40, y), line, font=fh, fill=(255, 255, 255))
        y += 78

    y += 20
    if utp:
        for line in _wrap(utp, fb_f, SIZE - 80, draw)[:3]:
            draw.text((40, y), line, font=fb_f, fill=(185, 215, 255))
            y += 46

    y += 16
    if geo:
        draw.text((40, y), f"📍 {geo}", font=fb_f, fill=(100, 160, 255))

    _cta_btn(draw, 40, SIZE - 120, cta_text, fc)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


# ── Публичная функция ─────────────────────────────────────────────────────────

def create_banners(image_bytes, headlines, bullets, cta):
    img = _prepare(image_bytes)
    variants = [
        ("Текст снизу",   style_bottom(img.copy(), headlines[0], bullets, cta)),
        ("Акцент сверху", style_accent(img.copy(), headlines[1], bullets, cta)),
        ("Текст сверху",  style_top(img.copy(),    headlines[2], bullets, cta)),
    ]
    result = []
    for label, composed in variants:
        buf = io.BytesIO()
        composed.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        result.append({"label": label, "image": f"data:image/png;base64,{b64}"})
    return result
