"""
treatments.py — три визуально разных макета из ОДНОГО фото.

Различие держится не на шрифте и не на цвете кнопки, а на трёх вещах
одновременно: кадрировании, грейде, структуре кадра. Только так три
креатива не считываются как один при пролистывании ленты.

    A. FULL BLEED  — фото на весь кадр, обычная крупность, текст в тихой зоне
    B. SPLIT FIELD — фото 56% кадра + плотное цветовое поле под текст
    C. MACRO       — экстремальный кроп детали + дуотон, типографика главная
"""

from __future__ import annotations

import os

import cv2
import numpy as np
from PIL import Image, ImageDraw

import adrender
import photo_ops as po

TMP = "/tmp/_ad"


def _save(img_bgr: np.ndarray, name: str) -> str:
    os.makedirs(TMP, exist_ok=True)
    p = os.path.join(TMP, name)
    cv2.imwrite(p, img_bgr)
    return p


def _darken(hex_color: str, factor: float = 0.30) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02X%02X%02X" % (int(r * factor), int(g * factor), int(b * factor))


def _pick_field_color(img_bgr: np.ndarray) -> str:
    """Плашка берёт цвет из самого кадра — макет выглядит цельным,
    а не как картинка с наклеенным прямоугольником."""
    for c in po.dominant_colors(img_bgr, 5):
        h = c.lstrip("#")
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        if max(r, g, b) - min(r, g, b) > 14:   # не серый
            return _darken(c, 0.26)
    return "#0C0E14"


# ─────────────────────────────────────────────────────────────────────────────
# A. FULL BLEED
# ─────────────────────────────────────────────────────────────────────────────

def treat_full_bleed(img_bgr, size, grade="premium_cold"):
    quiet = po.find_quiet_zone(img_bgr)
    zone = quiet["zone"]
    bg = po.smart_crop(img_bgr, size, zoom=1.0, reserve=zone)
    bg = po.grade(bg, grade)
    return _save(bg, "a_full.png"), {
        "safe_zone": zone,
        "overlay_treatment": "gradient_bottom",
        "_note": f"тихая зона: {zone}, шум {quiet['scores'][zone]:.3f}",
    }


# ─────────────────────────────────────────────────────────────────────────────
# B. SPLIT FIELD
# ─────────────────────────────────────────────────────────────────────────────

def treat_split_field(img_bgr, size, photo_share=0.58, grade="editorial_warm"):
    W, H = size
    ph = int(H * photo_share)
    photo = po.smart_crop(img_bgr, (W, ph), zoom=1.05, reserve="bottom")
    photo = po.grade(photo, grade)

    field_hex = _pick_field_color(img_bgr)
    h = field_hex.lstrip("#")
    field_bgr = tuple(int(h[i:i + 2], 16) for i in (4, 2, 0))

    canvas = np.zeros((H, W, 3), np.uint8)
    canvas[:, :] = field_bgr
    canvas[0:ph] = photo

    # мягкая растушёвка стыка
    blend = int(H * 0.035)
    for i in range(blend):
        t = i / blend
        y = ph - blend + i
        if 0 <= y < H:
            canvas[y] = (photo[min(y, ph-1)] * (1 - t) + np.array(field_bgr) * t).astype(np.uint8)

    return _save(canvas, "b_split.png"), {
        "safe_zone": "bottom",
        "overlay_treatment": "none",
        "primary_bg": field_hex,
        "_note": f"поле {field_hex}, фото {int(photo_share*100)}% кадра",
    }


# ─────────────────────────────────────────────────────────────────────────────
# C. MACRO + DUOTONE
# ─────────────────────────────────────────────────────────────────────────────

def treat_macro(img_bgr, size, zoom=2.3):
    bg = po.smart_crop(img_bgr, size, zoom=zoom, reserve="bottom")
    bg = po.grade(bg, "duotone")
    return _save(bg, "c_macro.png"), {
        "safe_zone": "bottom",
        "overlay_treatment": "gradient_bottom",
        "_note": f"макро-кроп ×{zoom}, дуотон",
    }


TREATMENTS = {
    "full_bleed":  treat_full_bleed,
    "split_field": treat_split_field,
    "macro":       treat_macro,
}

# Привязка приёма к температуре лида.
# hot  — товар и цена честно, во весь кадр
# warm — нужно место под буллеты и доказательства, поле их вмещает
# cold — нужен стоп-кадр, макро и дуотон ломают привычное восприятие
DEFAULT_MAP = {"hot": "full_bleed", "warm": "split_field", "cold": "macro"}


# ─────────────────────────────────────────────────────────────────────────────
# ОСНОВНОЙ ВХОДНОЙ ТОЧКА
# ─────────────────────────────────────────────────────────────────────────────

def render_from_photo(payload: dict, photo_path: str, out_dir: str,
                      strict: bool = True, restage_mode: str = "local",
                      niche: str = "", openai_client=None) -> dict:
    """payload — JSON креативного директора. photo_path — фото клиента.

    restage_mode:
        off        — фото используется как есть, только кроп и грейд
        local      — фон заменяется на студийный локально, бесплатно
        generative — фон дорисовывает gpt-image-1, с фолбэком на local
    """
    report = po.check_photo(photo_path)
    if strict and not report.ok:
        return {"status": "photo_rejected", "score": report.score,
                "problems": report.problems, "warnings": report.warnings,
                "meta": report.meta}

    raw = cv2.imread(photo_path)
    raw = po.auto_white_balance(raw)

    restage_report = {"restaged": False, "mode": "off"}
    if restage_mode != "off":
        import restage as rs
        if restage_mode == "generative" and openai_client is not None:
            raw, restage_report = rs.restage_generative(raw, niche, openai_client)
        else:
            raw, restage_report = rs.restage_local(raw)

    os.makedirs(out_dir, exist_ok=True)
    results = []

    for i, variant in enumerate(payload.get("variants", [])):
        temp = variant.get("lead_temperature", ["hot", "warm", "cold"][i % 3])
        tname = variant.get("treatment") or DEFAULT_MAP.get(temp, "full_bleed")
        ratio = variant.get("aspect_ratio", "4:5")
        size = adrender.FORMATS.get(ratio, adrender.FORMATS["4:5"])["size"]

        bg_path, patch = TREATMENTS[tname](raw, size)

        v = dict(variant)
        v["safe_zone"] = patch["safe_zone"]
        v["overlay_treatment"] = patch["overlay_treatment"]
        if "primary_bg" in patch:
            cs = dict(v.get("color_scheme", {}))
            cs["primary_bg"] = patch["primary_bg"]
            v["color_scheme"] = cs

        out = os.path.join(out_dir, f"{temp}_{tname}.png")
        adrender.render(v, bg_path, out, grain=True,
                        vignette=(tname != "split_field"))
        results.append({"file": out, "treatment": tname,
                        "temperature": temp, "note": patch["_note"]})

    return {"status": "ok", "score": report.score,
            "warnings": report.warnings, "meta": report.meta,
            "restage": restage_report, "results": results}
