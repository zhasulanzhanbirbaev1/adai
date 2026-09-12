"""
adrender.py — renders text overlay onto a prepared background image.
Works with the variant JSON from the creative director prompt.
"""
from __future__ import annotations

import os
import random

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ─────────────────────────────────────────────────────────────────────────────
# FORMAT REGISTRY
# ─────────────────────────────────────────────────────────────────────────────

FORMATS = {
    "4:5":  {"size": (1080, 1350), "label": "Instagram Feed"},
    "1:1":  {"size": (1080, 1080), "label": "Square"},
    "9:16": {"size": (1080, 1920), "label": "Stories / Reels"},
    "16:9": {"size": (1280, 720),  "label": "Facebook Cover"},
}

# ─────────────────────────────────────────────────────────────────────────────
# FONT HELPERS
# ─────────────────────────────────────────────────────────────────────────────

_BASE = os.path.join(os.path.dirname(__file__), "fonts")

_BOLD_CANDIDATES = [
    os.path.join(_BASE, "arialbd.ttf"),
    r"C:\Windows\Fonts\arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]
_REG_CANDIDATES = [
    os.path.join(_BASE, "arial.ttf"),
    r"C:\Windows\Fonts\arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


def _find(paths):
    for p in paths:
        if os.path.exists(p):
            return p
    return None


_F_BOLD = _find(_BOLD_CANDIDATES)
_F_REG  = _find(_REG_CANDIDATES)


def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    path = _F_BOLD if bold else _F_REG
    try:
        if path:
            return ImageFont.truetype(path, size)
    except Exception:
        pass
    return ImageFont.load_default()


def _wrap(text: str, font, max_w: int, draw: ImageDraw.ImageDraw) -> list[str]:
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


def _hex(h: str, fallback=(0, 0, 0)) -> tuple:
    try:
        h = h.lstrip("#")
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
    except Exception:
        return fallback


# ─────────────────────────────────────────────────────────────────────────────
# POST-PROCESSING EFFECTS
# ─────────────────────────────────────────────────────────────────────────────

def _add_grain(img: Image.Image, strength: float = 0.035) -> Image.Image:
    arr = np.array(img, dtype=np.float32)
    noise = np.random.normal(0, strength * 255, arr.shape)
    return Image.fromarray(np.clip(arr + noise, 0, 255).astype(np.uint8))


def _add_vignette(img: Image.Image, strength: float = 0.55) -> Image.Image:
    W, H = img.size
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    cx, cy = W / 2, H / 2
    r = np.sqrt(((xx - cx) / (W * 0.5)) ** 2 + ((yy - cy) / (H * 0.5)) ** 2)
    vig = np.clip(1.0 - r ** 2 * strength, 0, 1)[..., None]
    arr = np.array(img, dtype=np.float32) * vig
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def _gradient_overlay(img: Image.Image, zone: str, color=(0, 0, 0),
                       alpha_max: int = 210) -> Image.Image:
    W, H = img.size
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    r, g, b = color

    if zone in ("bottom", "top"):
        steps = int(H * 0.55)
        for i in range(steps):
            t = i / steps
            a = int(alpha_max * t)
            if zone == "bottom":
                y = H - steps + i
            else:
                y = steps - i - 1
            draw.line([(0, y), (W - 1, y)], fill=(r, g, b, a))
    elif zone in ("left", "right"):
        steps = int(W * 0.55)
        for i in range(steps):
            t = i / steps
            a = int(alpha_max * t)
            x = W - steps + i if zone == "right" else steps - i - 1
            draw.line([(x, 0), (x, H - 1)], fill=(r, g, b, a))

    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN RENDER
# ─────────────────────────────────────────────────────────────────────────────

def render(variant: dict, bg_path: str, out_path: str,
           grain: bool = True, vignette: bool = True) -> None:
    """
    Renders a complete ad banner.

    variant keys used:
      text_overlay  → city_tag, hook_headline, subheadline, bullets, cta_button
      color_scheme  → primary_bg, text_color, cta_bg, cta_text
      safe_zone     → "top" | "bottom" | "left" | "right"
      overlay_treatment → "gradient_bottom" | "none"
      font_style    → "bold_sans" | "elegant_serif" | "modern_display"
    """
    # Load background
    img = Image.open(bg_path).convert("RGB")
    W, H = img.size

    # Gradient
    ot = variant.get("overlay_treatment", "gradient_bottom")
    cs = variant.get("color_scheme", {})
    bg_color = _hex(cs.get("primary_bg", "#0C0E14"))

    if ot == "gradient_bottom":
        img = _gradient_overlay(img, "bottom", color=bg_color, alpha_max=205)
    elif ot == "gradient_top":
        img = _gradient_overlay(img, "top", color=bg_color, alpha_max=190)

    # Vignette
    if vignette:
        img = _add_vignette(img, strength=0.45)

    # Draw text
    draw = ImageDraw.Draw(img)
    txt = variant.get("text_overlay", {})
    safe = variant.get("safe_zone", "bottom")
    text_color = _hex(cs.get("text_color", "#FFFFFF"))
    cta_bg     = _hex(cs.get("cta_bg",    "#F97316"))
    cta_fg     = _hex(cs.get("cta_text",  "#FFFFFF"))

    margin = int(W * 0.06)
    text_w  = W - margin * 2

    # ── City tag (top-right pill) ───────────────────────────────────────────
    city = txt.get("city_tag", "")
    if city:
        ft_city = _font(int(W * 0.028), bold=False)
        bb = draw.textbbox((0, 0), city, font=ft_city)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        px, py = int(W * 0.028), int(W * 0.014)
        bw, bh = tw + px * 2, th + py * 2
        x0 = W - margin - bw
        y0 = int(H * 0.032)
        draw.rounded_rectangle([x0, y0, x0 + bw, y0 + bh],
                                radius=bh // 2, fill=(255, 255, 255, 200))
        draw.text((x0 + px, y0 + py), city, font=ft_city, fill=(20, 20, 30))

    # ── Text zone position ──────────────────────────────────────────────────
    if safe == "bottom":
        y = int(H * 0.54)
    elif safe == "top":
        y = int(H * 0.05)
    else:
        y = int(H * 0.54)

    # ── Headline ────────────────────────────────────────────────────────────
    headline = txt.get("hook_headline", "")
    if headline:
        fsize = int(W * 0.082)
        ft_h = _font(fsize, bold=True)
        lines = _wrap(headline, ft_h, text_w, draw)[:2]
        for line in lines:
            # Subtle text shadow
            draw.text((margin + 2, y + 2), line, font=ft_h, fill=(0, 0, 0, 120))
            draw.text((margin, y), line, font=ft_h, fill=text_color)
            y += int(fsize * 1.18)
        y += int(W * 0.018)

    # ── Subheadline ─────────────────────────────────────────────────────────
    sub = txt.get("subheadline", "")
    if sub:
        ft_s = _font(int(W * 0.042), bold=False)
        draw.text((margin, y), sub, font=ft_s, fill=(*text_color[:3], 210))
        y += int(W * 0.062)

    # ── Bullets ─────────────────────────────────────────────────────────────
    bullets = txt.get("bullets", [])
    if bullets:
        ft_b = _font(int(W * 0.038), bold=False)
        accent = _hex(cs.get("cta_bg", "#F97316"))
        for b in bullets[:3]:
            draw.text((margin, y), "▸  ", font=ft_b, fill=accent)
            draw.text((margin + int(W * 0.06), y), b, font=ft_b, fill=text_color)
            y += int(W * 0.052)
        y += int(W * 0.018)

    # ── CTA Button ──────────────────────────────────────────────────────────
    cta = txt.get("cta_button", "")
    if cta:
        ft_c = _font(int(W * 0.044), bold=True)
        bb = draw.textbbox((0, 0), cta, font=ft_c)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        px, py = int(W * 0.054), int(W * 0.022)
        bw, bh = tw + px * 2, th + py * 2
        # Place near bottom if safe zone is top
        if safe == "top":
            cy_btn = H - int(H * 0.09) - bh
        else:
            cy_btn = min(y + int(H * 0.015), H - bh - int(H * 0.04))
        draw.rounded_rectangle([margin, cy_btn, margin + bw, cy_btn + bh],
                                radius=bh // 2, fill=cta_bg)
        draw.text((margin + px, cy_btn + py), cta, font=ft_c, fill=cta_fg)

    # ── Film grain ──────────────────────────────────────────────────────────
    if grain:
        img = _add_grain(img, strength=0.022)

    img.save(out_path, format="PNG", optimize=False)
