from PIL import Image, ImageDraw, ImageFont, ImageFilter
import io, base64, os

FEED_W = 1080
FEED_H = 1350   # 4:5 — top Instagram engagement format

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


def _bottom_gradient(img: Image.Image, zone_frac=0.62, strength=238) -> Image.Image:
    W, H = img.size
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    start_y = int(H * (1 - zone_frac))
    zone_h  = H - start_y
    for i in range(zone_h):
        t = (i / zone_h) ** 1.25
        a = int(strength * t)
        d.line([(0, start_y + i), (W, start_y + i)], fill=(4, 7, 18, a))
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


def _pill(draw, x, y, text, font, bg=(37, 99, 235), fg=(255, 255, 255), pad_x=52, pad_y=20):
    bb = draw.textbbox((0, 0), text, font=font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    bw, bh = tw + pad_x * 2, th + pad_y * 2
    draw.rounded_rectangle([x, y, x + bw, y + bh], radius=bh // 2, fill=bg)
    draw.text((x + pad_x, y + pad_y), text, font=font, fill=fg)
    return bh


# ── Style 1: IMPACT ─────────────────────────────────────────────────────────
# Full-bleed portrait photo, cinematic bottom gradient, giant headline + CTA

def style_impact(img: Image.Image, headline: str, tagline: str, cta: str) -> Image.Image:
    W, H = img.size
    img = _bottom_gradient(img, zone_frac=0.65, strength=245)

    # Thin electric-blue accent bar at top
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, W, 8], fill=(37, 99, 235))

    fh = _font(F_BOLD, 98)
    ft = _font(F_REG,  44)
    fc = _font(F_BOLD, 46)
    margin = 60
    tw = W - margin * 2

    # Position text block starting from ~46% down
    y = int(H * 0.46)

    for line in _wrap(headline, fh, tw, draw)[:3]:
        draw.text((margin, y), line, font=fh, fill=(255, 255, 255))
        y += 112

    y += 14
    if tagline:
        for tl in _wrap(tagline, ft, tw, draw)[:2]:
            draw.text((margin, y), tl, font=ft, fill=(180, 210, 255))
            y += 56
        y += 16

    _pill(draw, margin, y, cta, fc, bg=(37, 99, 235))
    return img


# ── Style 2: PANEL ──────────────────────────────────────────────────────────
# Photo fills top 58%, deep navy panel with separator line at bottom

def style_panel(img: Image.Image, headline: str, bullets: list, cta: str) -> Image.Image:
    W, H = img.size
    split_y = int(H * 0.575)

    # Feather edge at bottom of photo
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    fade = 110
    for i in range(fade):
        a = int(255 * (i / fade) ** 1.5)
        d.line([(0, split_y - fade + i), (W, split_y - fade + i)], fill=(8, 14, 34, a))
    img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")

    draw = ImageDraw.Draw(img)
    draw.rectangle([0, split_y, W, H], fill=(8, 14, 34))
    draw.rectangle([0, split_y, W, split_y + 6], fill=(37, 99, 235))

    fh = _font(F_BOLD, 82)
    fb = _font(F_REG,  40)
    fc = _font(F_BOLD, 44)
    margin = 60
    tw = W - margin * 2
    y  = split_y + 38

    for line in _wrap(headline, fh, tw, draw)[:2]:
        draw.text((margin, y), line, font=fh, fill=(255, 255, 255))
        y += 96

    y += 10
    for b in (bullets or [])[:2]:
        draw.text((margin, y), f"✦  {b}", font=fb, fill=(100, 160, 255))
        y += 54

    y += 20
    # Centered CTA
    bb   = draw.textbbox((0, 0), cta, font=fc)
    tw2  = bb[2] - bb[0]; th2 = bb[3] - bb[1]
    px, py = 52, 18
    bw, bh = tw2 + px * 2, th2 + py * 2
    bx = (W - bw) // 2
    draw.rounded_rectangle([bx, y, bx + bw, y + bh], radius=bh // 2, fill=(37, 99, 235))
    draw.text((bx + px, y + py), cta, font=fc, fill=(255, 255, 255))
    return img


# ── Style 3: CARD ───────────────────────────────────────────────────────────
# Lightly blurred photo BG, frosted dark card with left accent stripe + CTA

def style_card(img: Image.Image, headline: str, tagline: str, cta: str) -> Image.Image:
    W, H = img.size

    bg = img.filter(ImageFilter.GaussianBlur(radius=5))
    tint = Image.new("RGB", (W, H), (5, 10, 25))
    bg = Image.blend(bg, tint, alpha=0.40)

    # Measure content to size the card
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    fh = _font(F_BOLD, 84)
    ft = _font(F_REG,  40)
    fc = _font(F_BOLD, 44)
    card_inner_w = W - 120 - 80   # 60px margin each side, 80px text padding inside

    h_lines = _wrap(headline, fh, card_inner_w, probe)[:3]
    t_lines = _wrap(tagline,  ft, card_inner_w, probe)[:2] if tagline else []

    content_h = len(h_lines) * 100 + len(t_lines) * 54 + 88 + 48   # headline + tagline + CTA + gaps
    card_h    = content_h + 80
    card_x0   = 60
    card_x1   = W - 60
    card_y0   = (H - card_h) // 2
    card_y1   = card_y0 + card_h

    # Frosted card overlay
    card_ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dc = ImageDraw.Draw(card_ov)
    dc.rounded_rectangle([card_x0, card_y0, card_x1, card_y1],
                          radius=26, fill=(9, 18, 48, 218))
    dc.rounded_rectangle([card_x0, card_y0, card_x0 + 7, card_y1],
                          radius=4, fill=(37, 99, 235, 255))

    result = Image.alpha_composite(bg.convert("RGBA"), card_ov).convert("RGB")
    draw   = ImageDraw.Draw(result)

    tx = card_x0 + 56
    y  = card_y0 + 44

    for line in h_lines:
        draw.text((tx, y), line, font=fh, fill=(255, 255, 255))
        y += 100

    y += 12
    for line in t_lines:
        draw.text((tx, y), line, font=ft, fill=(148, 182, 255))
        y += 54

    y += 22
    _pill(draw, tx, y, cta, fc, bg=(37, 99, 235))
    return result


# ── Direction creative (text-only) ──────────────────────────────────────────
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
    tw  = bb[2] - bb[0]; th = bb[3] - bb[1]
    px, py = 52, 18
    bw, bh = tw + px * 2, th + py * 2
    bx = (FEED_W - bw) // 2
    by = FEED_H - bh - 90
    draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=bh // 2, fill=(37, 99, 235))
    draw.text((bx + px, by + py), cta_txt, font=fc, fill=(255, 255, 255))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


# ── Public API ───────────────────────────────────────────────────────────────
def create_banners(image_bytes: bytes, headlines: list, bullets: list, cta: str) -> list:
    while len(headlines) < 3:
        headlines.append(headlines[0] if headlines else "Узнайте больше")

    tagline = bullets[0] if bullets else ""
    img = _cover_crop(image_bytes)   # 1080×1350

    variants = [
        ("Impact", style_impact(img.copy(), headlines[0], tagline, cta)),
        ("Panel",  style_panel(img.copy(),  headlines[1], bullets, cta)),
        ("Card",   style_card(img.copy(),   headlines[2], tagline, cta)),
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
