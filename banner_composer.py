from PIL import Image, ImageDraw, ImageFont, ImageFilter
import io, base64, os

FEED_W = 1080
FEED_H = 1350   # 4:5 — Instagram feed portrait (highest CTR)

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


# ── Helper: clean photo crop to given height ─────────────────────────────────
def _photo_area(base_img: Image.Image, photo_h: int) -> Image.Image:
    """Return clean top slice of the image — NO text or overlay."""
    return base_img.crop((0, 0, FEED_W, photo_h))


# ── Style 1: STAGE ───────────────────────────────────────────────────────────
# Clean photo top 60% | Near-black panel | Left-aligned headline + bullet + CTA

def style_stage(base: Image.Image, headline: str, bullets: list, cta: str) -> Image.Image:
    W, H = FEED_W, FEED_H
    PANEL_COLOR = (5, 9, 22)      # deep near-black with blue hint
    SPLIT = int(H * 0.60)         # 810px photo / 540px panel

    canvas = Image.new("RGB", (W, H), PANEL_COLOR)
    canvas.paste(_photo_area(base, SPLIT), (0, 0))

    draw = ImageDraw.Draw(canvas)
    # Accent separator
    draw.rectangle([0, SPLIT, W, SPLIT + 6], fill=(37, 99, 235))

    fh = _font(F_BOLD, 88)
    ft = _font(F_REG,  40)
    fc = _font(F_BOLD, 44)
    margin, tw = 60, W - 120
    y = SPLIT + 38

    for line in _wrap(headline, fh, tw, draw)[:2]:
        draw.text((margin, y), line, font=fh, fill=(255, 255, 255))
        y += 104

    y += 10
    if bullets:
        draw.text((margin, y), f"✦  {bullets[0]}", font=ft, fill=(148, 183, 255))
        y += 54

    y += 18
    _pill(draw, margin, y, cta, fc)
    return canvas


# ── Style 2: NAVY ────────────────────────────────────────────────────────────
# Clean photo top 57% | Navy gradient panel | Centered headline + 2 bullets + CTA

def style_navy(base: Image.Image, headline: str, bullets: list, cta: str) -> Image.Image:
    W, H = FEED_W, FEED_H
    SPLIT = int(H * 0.575)        # 776px photo / 574px panel

    canvas = Image.new("RGB", (W, H), (10, 22, 50))
    canvas.paste(_photo_area(base, SPLIT), (0, 0))

    draw = ImageDraw.Draw(canvas)
    # Gradient panel background
    for i in range(H - SPLIT):
        t = i / (H - SPLIT)
        r = int(10  * (1 - t) + 4  * t)
        g = int(22  * (1 - t) + 12 * t)
        b = int(50  * (1 - t) + 22 * t)
        draw.line([(0, SPLIT + i), (W, SPLIT + i)], fill=(r, g, b))

    # Thin white hairline separator
    draw.rectangle([0, SPLIT, W, SPLIT + 2], fill=(255, 255, 255, 80))

    fh = _font(F_BOLD, 82)
    ft = _font(F_REG,  38)
    fc = _font(F_BOLD, 42)
    margin, tw = 60, W - 120
    y = SPLIT + 38

    # Centered headline
    for line in _wrap(headline, fh, tw, draw)[:2]:
        bb = draw.textbbox((0, 0), line, font=fh)
        lw = bb[2] - bb[0]
        draw.text(((W - lw) // 2, y), line, font=fh, fill=(255, 255, 255))
        y += 96

    y += 8
    for b in (bullets or [])[:2]:
        draw.text((margin, y), f"→  {b}", font=ft, fill=(147, 197, 253))
        y += 50

    y += 22
    _pill_center(draw, W, y, cta, fc)
    return canvas


# ── Style 3: FRAME ───────────────────────────────────────────────────────────
# Clean photo top 57% with white top bar | Charcoal panel | Bold layout + CTA

def style_frame(base: Image.Image, headline: str, bullets: list, cta: str) -> Image.Image:
    W, H = FEED_W, FEED_H
    SPLIT = int(H * 0.570)        # 769px photo / 581px panel

    canvas = Image.new("RGB", (W, H), (14, 14, 18))
    canvas.paste(_photo_area(base, SPLIT), (0, 0))

    draw = ImageDraw.Draw(canvas)
    # White top accent bar on photo (brand touch)
    draw.rectangle([0, 0, W, 9], fill=(255, 255, 255))
    # Blue left-side accent on panel
    draw.rectangle([0, SPLIT, 7, H], fill=(37, 99, 235))

    fh = _font(F_BOLD, 84)
    ft = _font(F_REG,  40)
    fc = _font(F_BOLD, 42)
    margin, tw = 60, W - 130
    y = SPLIT + 38

    for line in _wrap(headline, fh, tw, draw)[:2]:
        draw.text((margin, y), line, font=fh, fill=(255, 255, 255))
        y += 100

    y += 14
    for b in (bullets or [])[:2]:
        draw.text((margin, y), f"•  {b}", font=ft, fill=(180, 180, 200))
        y += 52

    y += 22
    _pill(draw, margin, y, cta, fc)
    return canvas


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

    base = _cover_crop(image_bytes)   # 1080×1350 full canvas

    variants = [
        ("Stage", style_stage(base.copy(), headlines[0], bullets, cta)),
        ("Navy",  style_navy(base.copy(),  headlines[1], bullets, cta)),
        ("Frame", style_frame(base.copy(), headlines[2], bullets, cta)),
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
