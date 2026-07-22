from PIL import Image, ImageDraw, ImageFont, ImageFilter
import io, base64, os

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


def _prepare(image_bytes: bytes) -> Image.Image:
    img  = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    w, h = img.size
    side = min(w, h)
    img  = img.crop(((w-side)//2, (h-side)//2, (w+side)//2, (h+side)//2))
    return img.resize((SIZE, SIZE), Image.LANCZOS)


def _gradient_overlay(img, direction="bottom", strength=220):
    overlay = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    zone = int(SIZE * 0.60)
    for i in range(zone):
        a = int(strength * (i / zone) ** 1.4)
        if direction == "bottom":
            d.line([(0, SIZE-zone+i), (SIZE, SIZE-zone+i)], fill=(0, 0, 0, a))
        else:
            d.line([(0, zone-i-1), (SIZE, zone-i-1)], fill=(0, 0, 0, a))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def _accent_bar(img, color=(37, 99, 235)):
    ov = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(ov).rectangle([0, 0, SIZE, 8], fill=(*color, 255))
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


def _cta_pill(draw, x, y, text, font, color=(37, 99, 235)):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    pad_x, pad_y = 36, 16
    w = tw + pad_x * 2
    h = th + pad_y * 2
    draw.rounded_rectangle([x, y, x+w, y+h], radius=h//2, fill=color)
    draw.text((x + pad_x, y + pad_y), text, font=font, fill=(255, 255, 255))
    return h


# ── Style 1: Premium Bottom — dark gradient, large headline, bullets, pill CTA ─

def style_premium_bottom(img, headline, bullets, cta):
    img  = _gradient_overlay(img, direction="bottom", strength=230)
    img  = _accent_bar(img, color=(37, 99, 235))
    draw = ImageDraw.Draw(img)

    fh = _font(F_BOLD, 72)
    fb = _font(F_REG, 36)
    fc = _font(F_BOLD, 38)

    margin = 48
    y = int(SIZE * 0.46)

    for line in _wrap(headline, fh, SIZE - margin*2, draw)[:2]:
        draw.text((margin, y), line, font=fh, fill=(255, 255, 255))
        y += 84

    y += 8
    for b in bullets[:3]:
        draw.text((margin, y), f"✓  {b}", font=fb, fill=(147, 197, 253))
        y += 48

    y += 16
    _cta_pill(draw, margin, y, cta, fc, color=(37, 99, 235))
    return img


# ── Style 2: Split — top logo bar + bottom text block with semi-transparent bg ─

def style_split(img, headline, bullets, cta):
    img  = _gradient_overlay(img, direction="bottom", strength=240)
    draw = ImageDraw.Draw(img)

    # Top accent stripe
    ov = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(ov).rectangle([0, 0, SIZE, 90], fill=(37, 99, 235, 220))
    img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
    draw = ImageDraw.Draw(img)

    fa = _font(F_BOLD, 36)
    fh = _font(F_BOLD, 68)
    fb = _font(F_REG, 34)
    fc = _font(F_BOLD, 36)

    # Top bar text
    if bullets:
        draw.text((48, 26), bullets[0].upper(), font=fa, fill=(255, 255, 255))

    margin = 48
    y = int(SIZE * 0.50)

    for line in _wrap(headline, fh, SIZE - margin*2, draw)[:2]:
        draw.text((margin, y), line, font=fh, fill=(255, 255, 255))
        y += 80

    y += 10
    for b in bullets[1:3]:
        draw.text((margin, y), f"→  {b}", font=fb, fill=(186, 230, 253))
        y += 46

    y += 18
    _cta_pill(draw, margin, y, cta, fc, color=(37, 99, 235))
    return img


# ── Style 3: Minimal Top — clean top-heavy layout, white headline ──────────────

def style_minimal_top(img, headline, bullets, cta):
    img  = _gradient_overlay(img, direction="top", strength=210)
    img  = _accent_bar(img, color=(37, 99, 235))
    draw = ImageDraw.Draw(img)

    fh = _font(F_BOLD, 70)
    fb = _font(F_REG, 34)
    fc = _font(F_BOLD, 36)

    margin = 48
    y = 28

    for line in _wrap(headline, fh, SIZE - margin*2, draw)[:2]:
        draw.text((margin, y), line, font=fh, fill=(255, 255, 255))
        y += 82

    y += 10
    for b in bullets[:3]:
        draw.text((margin, y), f"•  {b}", font=fb, fill=(186, 230, 253))
        y += 46

    y += 18
    _cta_pill(draw, margin, y, cta, fc, color=(37, 99, 235))
    return img


# ── Text-only banner for directions (no photo) ────────────────────────────────

def generate_creative_for_direction(direction: dict) -> bytes:
    img = Image.new("RGB", (SIZE, SIZE), (6, 12, 28))
    draw = ImageDraw.Draw(img)

    for i in range(SIZE):
        r = int(6 + (15 - 6) * i / SIZE)
        g = int(12 + (25 - 12) * i / SIZE)
        b = int(28 + (70 - 28) * i / SIZE)
        draw.line([(0, i), (SIZE, i)], fill=(r, g, b))

    draw.rectangle([0, 0, SIZE, 10], fill=(37, 99, 235))

    fh = _font(F_BOLD, 64)
    fb = _font(F_REG, 36)
    fc = _font(F_BOLD, 38)

    name = direction.get("name", "Реклама")
    utp  = direction.get("utp", "")
    geo  = direction.get("geo", "Казахстан")
    traffic = direction.get("traffic_dest", "whatsapp")
    cta_text = "Написать в WhatsApp" if traffic == "whatsapp" else "Узнать подробнее"

    y = 60
    for line in _wrap(name, fh, SIZE - 80, draw)[:3]:
        draw.text((40, y), line, font=fh, fill=(255, 255, 255))
        y += 78

    y += 20
    if utp:
        for line in _wrap(utp, fb, SIZE - 80, draw)[:3]:
            draw.text((40, y), line, font=fb, fill=(147, 197, 253))
            y += 46

    y += 16
    if geo:
        draw.text((40, y), f"📍 {geo}", font=fb, fill=(100, 160, 255))

    _cta_pill(draw, 40, SIZE - 130, cta_text, fc, color=(37, 99, 235))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


# ── Public API ────────────────────────────────────────────────────────────────

def create_banners(image_bytes, headlines, bullets, cta):
    while len(headlines) < 3:
        headlines.append(headlines[0] if headlines else "")

    img = _prepare(image_bytes)
    variants = [
        ("Premium",  style_premium_bottom(img.copy(), headlines[0], bullets, cta)),
        ("Split",    style_split(img.copy(),          headlines[1], bullets, cta)),
        ("Minimal",  style_minimal_top(img.copy(),    headlines[2], bullets, cta)),
    ]
    result = []
    for label, composed in variants:
        buf = io.BytesIO()
        composed.save(buf, format="JPEG", quality=92)
        b64 = base64.b64encode(buf.getvalue()).decode()
        result.append({"label": label, "image": f"data:image/jpeg;base64,{b64}"})
    return result
