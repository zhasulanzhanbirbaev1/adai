"""
photo_ops.py — low-level computer vision utilities for banner pipeline.
All functions operate on BGR numpy arrays (OpenCV convention).
"""
from __future__ import annotations

import io
import os
from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image


# ─────────────────────────────────────────────────────────────────────────────
# WHITE BALANCE
# ─────────────────────────────────────────────────────────────────────────────

def auto_white_balance(img: np.ndarray) -> np.ndarray:
    """Grey-world white balance. Corrects colour casts from phone cameras."""
    result = img.astype(np.float32)
    mean_b = result[:, :, 0].mean()
    mean_g = result[:, :, 1].mean()
    mean_r = result[:, :, 2].mean()
    mean_all = (mean_b + mean_g + mean_r) / 3.0
    if mean_b > 0: result[:, :, 0] *= mean_all / mean_b
    if mean_g > 0: result[:, :, 1] *= mean_all / mean_g
    if mean_r > 0: result[:, :, 2] *= mean_all / mean_r
    return np.clip(result, 0, 255).astype(np.uint8)


# ─────────────────────────────────────────────────────────────────────────────
# FACE DETECTION
# ─────────────────────────────────────────────────────────────────────────────

_face_cascade = None

def _get_face_cascade():
    global _face_cascade
    if _face_cascade is None:
        xml = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        _face_cascade = cv2.CascadeClassifier(xml)
    return _face_cascade


def detect_faces(img: np.ndarray) -> list[tuple]:
    """Returns list of (x, y, w, h) face rectangles."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = _get_face_cascade().detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5,
        minSize=(60, 60), flags=cv2.CASCADE_SCALE_IMAGE
    )
    return list(faces) if len(faces) > 0 else []


# ─────────────────────────────────────────────────────────────────────────────
# SALIENCY MAP
# ─────────────────────────────────────────────────────────────────────────────

def saliency_map(img: np.ndarray) -> np.ndarray:
    """Spectral residual saliency — fast, no ML model needed."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    L = lab[:, :, 0].astype(np.float32)

    # Spectral residual in log-amplitude domain
    small = cv2.resize(L, (64, 64), interpolation=cv2.INTER_AREA)
    dft = np.fft.fft2(small)
    log_amp = np.log(np.abs(dft) + 1e-8)
    phase = np.angle(dft)
    avg_amp = cv2.blur(log_amp, (3, 3))
    residual = np.exp(log_amp - avg_amp)
    reconstructed = np.abs(np.fft.ifft2(residual * np.exp(1j * phase))) ** 2
    sal_small = cv2.GaussianBlur(reconstructed.astype(np.float32), (5, 5), 0)
    sal = cv2.resize(sal_small, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_CUBIC)

    # Boost faces
    for (x, y, w, h) in detect_faces(img):
        y0 = max(0, y - int(h * 0.3))
        y1 = min(sal.shape[0], y + int(h * 3))
        x0 = max(0, x - int(w * 0.5))
        x1 = min(sal.shape[1], x + w + int(w * 0.5))
        sal[y0:y1, x0:x1] *= 2.5

    # Normalise
    mn, mx = sal.min(), sal.max()
    if mx > mn:
        sal = (sal - mn) / (mx - mn)
    return sal.astype(np.float32)


# ─────────────────────────────────────────────────────────────────────────────
# DOMINANT COLOURS
# ─────────────────────────────────────────────────────────────────────────────

def dominant_colors(img: np.ndarray, n: int = 5) -> list[str]:
    """Returns n dominant colours as '#RRGGBB' hex strings (sorted by dominance)."""
    small = cv2.resize(img, (120, 120), interpolation=cv2.INTER_AREA)
    pixels = small.reshape(-1, 3).astype(np.float32)

    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.5)
    k = min(n, len(pixels))
    _, labels, centers = cv2.kmeans(
        pixels, k, None, criteria, 5, cv2.KMEANS_PP_CENTERS
    )
    counts = np.bincount(labels.flatten(), minlength=k)
    order = np.argsort(-counts)
    result = []
    for i in order:
        b, g, r = (int(c) for c in centers[i])
        result.append(f"#{r:02X}{g:02X}{b:02X}")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# QUIET ZONE DETECTION  (where to put text safely)
# ─────────────────────────────────────────────────────────────────────────────

def find_quiet_zone(img: np.ndarray) -> dict:
    """
    Finds the area with least visual noise/saliency — safest for text.
    Returns {"zone": "top"|"bottom"|"left"|"right", "scores": {zone: score}}.
    Low score = quieter = better for text.
    """
    sal = saliency_map(img)
    H, W = sal.shape
    cut = 0.38

    scores = {
        "top":    float(sal[:int(H * cut), :].mean()),
        "bottom": float(sal[int(H * (1 - cut)):, :].mean()),
        "left":   float(sal[:, :int(W * cut)].mean()),
        "right":  float(sal[:, int(W * (1 - cut)):].mean()),
    }
    # Prefer vertical zones (top/bottom) for portrait format
    best = min(scores, key=lambda z: scores[z] * (0.8 if z in ("top", "bottom") else 1.0))
    return {"zone": best, "scores": scores}


# ─────────────────────────────────────────────────────────────────────────────
# SMART CROP
# ─────────────────────────────────────────────────────────────────────────────

def smart_crop(img: np.ndarray, size: tuple, zoom: float = 1.0,
               reserve: str = "bottom") -> np.ndarray:
    """
    Content-aware crop: centres on the most salient region,
    then anchors one side to `reserve` so text has breathing room.
    """
    W, H = size
    ih, iw = img.shape[:2]

    # Scale so image fills target at zoom level
    scale = max(W / iw, H / ih) * zoom
    nw, nh = max(int(iw * scale), W), max(int(ih * scale), H)
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LANCZOS4)

    # Find salient centre
    sal = saliency_map(resized)
    ys, xs = np.where(sal > np.percentile(sal, 75))
    if len(xs) > 0:
        cx = int(xs.mean())
        cy = int(ys.mean())
    else:
        cx, cy = nw // 2, nh // 2

    # Crop window centred on salient point
    x0 = int(np.clip(cx - W // 2, 0, nw - W))
    y0 = int(np.clip(cy - H // 2, 0, nh - H))

    # Apply reserve: anchor one edge so text zone stays clear
    if reserve == "bottom":
        y0 = max(0, min(y0, nh - H))           # allow subject to sit high
    elif reserve == "top":
        y0 = max(nh - H, 0)
    elif reserve == "left":
        x0 = max(nw - W, 0)
    elif reserve == "right":
        x0 = 0

    return resized[y0:y0 + H, x0:x0 + W]


# ─────────────────────────────────────────────────────────────────────────────
# COLOUR GRADING
# ─────────────────────────────────────────────────────────────────────────────

def _apply_curves(img: np.ndarray, curve: np.ndarray) -> np.ndarray:
    lut = np.clip(curve, 0, 255).astype(np.uint8)
    return cv2.LUT(img, lut)


def grade(img: np.ndarray, preset: str = "premium_cold") -> np.ndarray:
    """
    Presets:
      premium_cold   — desaturated cool, lifted shadows (Apple/luxury)
      editorial_warm — warm golden hour, rich shadows (Airbnb/lifestyle)
      duotone        — high-contrast teal & orange split-tone
      clean_neutral  — gentle contrast lift, neutral tone
    """
    x = np.arange(256, dtype=np.float32)
    result = img.astype(np.float32)

    if preset == "premium_cold":
        # Slightly crush shadows, cool highlights
        curve = np.clip(x * 0.90 + 12, 0, 255)
        result = _apply_curves(img, curve)
        hsv = cv2.cvtColor(result, cv2.COLOR_BGR2HSV).astype(np.float32)
        hsv[:, :, 1] *= 0.78         # desaturate
        hsv[:, :, 2] = np.clip(hsv[:, :, 2] * 1.06, 0, 255)
        result = cv2.cvtColor(np.clip(hsv, 0, 255).astype(np.uint8), cv2.COLOR_HSV2BGR)
        result[:, :, 0] = np.clip(result[:, :, 0].astype(np.float32) * 1.04, 0, 255)  # boost blue

    elif preset == "editorial_warm":
        curve = np.clip(x * 0.92 + 10, 0, 255)
        result = _apply_curves(img, curve)
        hsv = cv2.cvtColor(result, cv2.COLOR_BGR2HSV).astype(np.float32)
        hsv[:, :, 1] = np.clip(hsv[:, :, 1] * 1.15, 0, 255)
        result = cv2.cvtColor(np.clip(hsv, 0, 255).astype(np.uint8), cv2.COLOR_HSV2BGR)
        result[:, :, 2] = np.clip(result[:, :, 2].astype(np.float32) * 1.06, 0, 255)  # warm reds

    elif preset == "duotone":
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
        teal   = np.array([150, 120, 30],  dtype=np.float32)   # BGR
        orange = np.array([30,  90, 220],  dtype=np.float32)   # BGR
        out = np.zeros((*gray.shape, 3), dtype=np.float32)
        for c in range(3):
            out[:, :, c] = gray * orange[c] + (1 - gray) * teal[c]
        result = np.clip(out, 0, 255).astype(np.uint8)

    elif preset == "clean_neutral":
        curve = np.clip(x * 0.94 + 8, 0, 255)
        result = _apply_curves(img, curve)

    else:
        return img

    return result.astype(np.uint8)


# ─────────────────────────────────────────────────────────────────────────────
# PHOTO QUALITY CHECK
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PhotoReport:
    ok: bool
    score: float          # 0–100
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


def check_photo(path: str, min_w: int = 600, min_h: int = 600) -> PhotoReport:
    """Quality gate: resolution, blur, exposure."""
    img = cv2.imread(path)
    if img is None:
        return PhotoReport(ok=False, score=0, problems=["Файл не читается"])

    H, W = img.shape[:2]
    problems, warnings = [], []
    score = 100.0

    # Resolution
    if W < min_w or H < min_h:
        problems.append(f"Слишком маленькое фото ({W}×{H}). Минимум {min_w}×{min_h}.")
        score -= 40

    # Blur (Laplacian variance)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
    if blur_score < 60:
        problems.append("Фото размытое. Снимите заново, держа телефон неподвижно.")
        score -= 30
    elif blur_score < 120:
        warnings.append("Фото немного размытое — результат будет хуже.")
        score -= 10

    # Exposure
    mean_v = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[:, :, 2].mean()
    if mean_v < 45:
        problems.append("Фото слишком тёмное. Снимите при лучшем освещении.")
        score -= 25
    elif mean_v < 80:
        warnings.append("Недостаточно света — лучше снять при дневном освещении.")
        score -= 8
    elif mean_v > 220:
        warnings.append("Фото пересвечено.")
        score -= 8

    score = max(0.0, score)
    ok = len(problems) == 0 and score >= 50

    return PhotoReport(
        ok=ok,
        score=round(score, 1),
        problems=problems,
        warnings=warnings,
        meta={"width": W, "height": H, "blur": round(blur_score, 1), "brightness": round(float(mean_v), 1)},
    )
