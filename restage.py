"""
restage.py — превращает телефонное фото клиента в рекламный кадр.

Задача: убрать шлам, заменить фон, поставить свет — но не трогать сам товар.

Два пути:
  local      — фон синтезируется локально (студийный градиент, падающая тень).
               Бесплатно, мгновенно, без сети. Хорошо для товара и еды.
  generative — фон дорисовывает gpt-image-1 через edits с маской.
               Красивее и медленнее, но даёт настоящую среду.

ЖЕЛЕЗНОЕ ПРАВИЛО
Пиксели объекта не меняются никогда. Если нейросеть перерисует товар,
клиент получит заявки на то, чего у него нет. Для медицины это ещё и
недостоверная реклама. Поэтому объект защищён маской, а результат
генерации проверяется на дрейф и отклоняется, если товар поплыл.
"""

from __future__ import annotations

import base64
import io
import os
from dataclasses import dataclass

import cv2
import numpy as np

import photo_ops as po


# ─────────────────────────────────────────────────────────────────────────────
# 1. ВЫРЕЗАНИЕ ОБЪЕКТА
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Cutout:
    mask: np.ndarray        # 0..255, float-совместимая альфа
    bbox: tuple             # x, y, w, h
    coverage: float         # доля кадра, занятая объектом
    confident: bool         # можно ли доверять вырезке


def _saliency_bbox(img: np.ndarray, q: float = 78.0) -> tuple:
    """Стартовый прямоугольник для GrabCut по карте внимания."""
    H, W = img.shape[:2]
    sal = po.saliency_map(img)

    for (x, y, fw, fh) in po.detect_faces(img):
        y0 = max(0, y - int(fh * 0.6))
        y1 = min(H, y + int(fh * 4.2))
        x0 = max(0, x - int(fw * 1.1))
        x1 = min(W, x + fw + int(fw * 1.1))
        sal[y0:y1, x0:x1] += 1.5

    thr = np.percentile(sal, q)
    binary = (sal >= thr).astype(np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
    if n <= 1:
        return (int(W * 0.15), int(H * 0.15), int(W * 0.7), int(H * 0.7))

    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y, w, h = stats[i, :4]
    pad_x, pad_y = int(w * 0.10), int(h * 0.10)
    x = max(0, x - pad_x); y = max(0, y - pad_y)
    w = min(W - x, w + pad_x * 2); h = min(H - y, h + pad_y * 2)
    return (int(x), int(y), int(w), int(h))


def _feather(mask: np.ndarray, img: np.ndarray, radius: int = 3) -> np.ndarray:
    """Смягчение краёв по границам изображения."""
    m = mask.astype(np.float32) / 255.0
    m = cv2.GaussianBlur(m, (0, 0), radius)
    guide = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    for _ in range(2):
        if hasattr(cv2, "ximgproc"):
            m = cv2.ximgproc.guidedFilter(guide, m, 8, 1e-3)
        else:
            m = cv2.bilateralFilter(m, 9, 0.1, 9)
    return np.clip(m * 255, 0, 255).astype(np.uint8)


def segment_subject(img: np.ndarray, iters: int = 6) -> Cutout:
    """GrabCut, инициализированный по карте внимания."""
    H, W = img.shape[:2]
    rect = _saliency_bbox(img)

    mask = np.zeros((H, W), np.uint8)
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(img, mask, rect, bgd, fgd, iters, cv2.GC_INIT_WITH_RECT)
    except cv2.error:
        m = np.zeros((H, W), np.uint8)
        x, y, w, h = rect
        m[y:y + h, x:x + w] = 255
        return Cutout(m, rect, w * h / (W * H), False)

    binary = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN,  np.ones((5, 5),  np.uint8))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((21, 21), np.uint8))

    n, labels, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
    if n > 1:
        i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        binary = np.where(labels == i, 255, 0).astype(np.uint8)

    alpha = _feather(binary, img)
    ys, xs = np.where(binary > 127)
    if len(xs) == 0:
        return Cutout(binary, rect, 0.0, False)

    bbox = (int(xs.min()), int(ys.min()),
            int(xs.max() - xs.min()), int(ys.max() - ys.min()))
    coverage = float((binary > 127).sum()) / (W * H)
    touch = sum([bbox[0] < 4, bbox[1] < 4,
                 bbox[0] + bbox[2] > W - 4, bbox[1] + bbox[3] > H - 4])
    confident = 0.06 < coverage < 0.82 and touch <= 2
    return Cutout(alpha, bbox, coverage, confident)


# ─────────────────────────────────────────────────────────────────────────────
# 2. СТУДИЙНЫЙ ФОН
# ─────────────────────────────────────────────────────────────────────────────

def studio_background(size, base_bgr=(46, 44, 42), warm: bool = True,
                      light_x: float = 0.38) -> np.ndarray:
    """Неровный фон с мягким световым пятном."""
    W, H = size
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    cx, cy = W * light_x, H * 0.34
    r = np.sqrt(((xx - cx) / (W * 0.85)) ** 2 + ((yy - cy) / (H * 0.85)) ** 2)
    fall = np.clip(1.0 - r ** 1.5, 0.0, 1.0)

    bg = np.zeros((H, W, 3), np.float32)
    hi = np.array(base_bgr, np.float32) * 2.5
    lo = np.array(base_bgr, np.float32) * 0.55
    if warm:
        hi = hi * np.array([0.92, 1.0, 1.08], np.float32)
    for c in range(3):
        bg[:, :, c] = lo[c] + (hi[c] - lo[c]) * fall

    horizon = int(H * 0.68)
    floor = np.linspace(0.0, 1.0, H - horizon, dtype=np.float32)[:, None, None]
    bg[horizon:] *= (1.0 - 0.22 * floor)

    bg = cv2.GaussianBlur(bg, (0, 0), W * 0.012)
    return np.clip(bg, 0, 255).astype(np.uint8)


def contact_shadow(alpha: np.ndarray, strength: float = 0.55,
                   spread: float = 0.035, lift: float = 0.012) -> np.ndarray:
    """Падающая тень под объектом."""
    H, W = alpha.shape
    a = alpha.astype(np.float32) / 255.0
    sh = cv2.GaussianBlur(a, (0, 0), W * spread)
    M = np.float32([[1, 0, W * 0.006], [0, 1, H * lift]])
    sh = cv2.warpAffine(sh, M, (W, H))
    grad = np.linspace(0.35, 1.0, H, dtype=np.float32)[:, None]
    return np.clip(sh * grad * strength, 0, 1)


def composite(subject: np.ndarray, alpha: np.ndarray,
              bg: np.ndarray, shadow: np.ndarray | None = None) -> np.ndarray:
    a = (alpha.astype(np.float32) / 255.0)[..., None]
    out = bg.astype(np.float32)
    if shadow is not None:
        out *= (1.0 - shadow[..., None] * 0.85)
    out = subject.astype(np.float32) * a + out * (1 - a)
    return np.clip(out, 0, 255).astype(np.uint8)


def match_subject_to_bg(subject: np.ndarray, alpha: np.ndarray,
                        bg: np.ndarray) -> np.ndarray:
    """Мягкий сдвиг цвета объекта под свет фона."""
    a = alpha > 127
    if a.sum() < 100:
        return subject
    out = subject.astype(np.float32)
    bg_mean  = bg.reshape(-1, 3).mean(axis=0)
    sub_mean = subject[a].mean(axis=0)
    shift = (bg_mean - sub_mean) * 0.18
    out += shift
    return np.clip(out, 0, 255).astype(np.uint8)


def restage_local(img: np.ndarray, palette_bgr=None,
                  target_coverage: float = 0.52) -> tuple:
    """Полная локальная пересъёмка. Возвращает (кадр, отчёт)."""
    H, W = img.shape[:2]
    cut = segment_subject(img)
    if not cut.confident:
        return img, {"restaged": False,
                     "reason": "объект не выделился уверенно",
                     "coverage": round(cut.coverage, 3)}

    x, y, w, h = cut.bbox
    subject = img[y:y + h, x:x + w]
    alpha   = cut.mask[y:y + h, x:x + w]

    scale = np.sqrt(target_coverage * W * H / max(w * h, 1))
    scale = min(scale, (H * 0.64) / max(h, 1), (W * 0.82) / max(w, 1))
    scale = float(np.clip(scale, 0.3, 2.0))
    nw, nh = max(int(w * scale), 8), max(int(h * scale), 8)
    interp = cv2.INTER_LANCZOS4 if scale > 1 else cv2.INTER_AREA
    subject = cv2.resize(subject, (nw, nh), interpolation=interp)
    alpha   = cv2.resize(alpha,   (nw, nh), interpolation=cv2.INTER_LINEAR)

    base = palette_bgr or (46, 44, 42)
    bg = studio_background((W, H), base)

    canvas_sub = np.zeros_like(img)
    canvas_a   = np.zeros((H, W), np.uint8)
    ox = (W - nw) // 2
    oy = int(H * 0.80) - nh
    oy = int(np.clip(oy, int(H * 0.04), max(H - nh, 0)))
    ox = int(np.clip(ox, 0, max(W - nw, 0)))
    ph, pw = min(nh, H - oy), min(nw, W - ox)
    canvas_sub[oy:oy + ph, ox:ox + pw] = subject[:ph, :pw]
    canvas_a[oy:oy + ph, ox:ox + pw]   = alpha[:ph, :pw]

    canvas_sub = match_subject_to_bg(canvas_sub, canvas_a, bg)
    shadow = contact_shadow(canvas_a)
    out = composite(canvas_sub, canvas_a, bg, shadow)

    return out, {"restaged": True, "mode": "local",
                 "coverage": round(cut.coverage, 3),
                 "scale": round(scale, 2)}


# ─────────────────────────────────────────────────────────────────────────────
# 3. ГЕНЕРАТИВНЫЙ ФОН (gpt-image-1 edits)
# ─────────────────────────────────────────────────────────────────────────────

def build_edit_mask(alpha: np.ndarray, grow: int = 6) -> bytes:
    """Маска для gpt-image-1 edits: ПРОЗРАЧНОЕ — то, что модель может перерисовать."""
    from PIL import Image as PILImage
    k = np.ones((grow * 2 + 1,) * 2, np.uint8)
    protect = cv2.dilate((alpha > 127).astype(np.uint8) * 255, k)
    rgba = np.zeros((*alpha.shape, 4), np.uint8)
    rgba[..., 3] = 255 - protect
    buf = io.BytesIO()
    PILImage.fromarray(rgba, "RGBA").save(buf, format="PNG")
    return buf.getvalue()


def background_prompt(niche: str) -> str:
    """Промпт описывает ТОЛЬКО среду. Ни слова о самом товаре."""
    scenes = {
        "стоматология": "clean modern dental clinic interior, soft neutral walls, "
                        "shallow depth of field, soft diffused lighting",
        "автосервис":   "professional service bay, dark polished concrete floor, "
                        "controlled industrial lighting, cinematic",
        "салон красоты": "warm minimal beauty salon interior, wood and matte surfaces, "
                          "soft window light",
        "цветочный":    "bright airy studio, pale linen backdrop, soft natural light",
        "общепит":      "warm restaurant interior, warm bokeh lights in background",
        "фитнес":       "modern gym interior, dark tones, dramatic side lighting",
    }
    scene = scenes.get(niche.lower(), "seamless studio backdrop, neutral warm tone")
    return (f"Replace only the background with: {scene}. "
            "Soft directional light from the left, gentle falloff, "
            "natural contact shadow on the surface below the subject. "
            "Photorealistic advertising photography, shot on 85mm f/1.8. "
            "Do not add any text, letters, numbers, logos or signage. "
            "Do not alter, redraw or replace the main subject in any way.")


def verify_subject_unchanged(before: np.ndarray, after: np.ndarray,
                             alpha: np.ndarray, tol: float = 6.0) -> tuple:
    """Проверяет что gpt-image-1 не перерисовал товар. Если поплыл — фолбэк."""
    if before.shape != after.shape:
        after = cv2.resize(after, (before.shape[1], before.shape[0]))
    m = alpha > 127
    if m.sum() < 100:
        return False, 999.0
    d = np.abs(before.astype(np.float32) - after.astype(np.float32))
    drift = float(d[m].mean())
    return drift <= tol, round(drift, 2)


def restage_generative(img: np.ndarray, niche: str, openai_client,
                       size: str = "1024x1536") -> tuple:
    """Замена фона через gpt-image-1 edits с защитной маской."""
    cut = segment_subject(img)
    if not cut.confident:
        out, rep = restage_local(img)
        rep["fallback_from"] = "generative: объект не выделился"
        return out, rep

    try:
        from PIL import Image as PILImage
        buf = io.BytesIO()
        PILImage.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).save(buf, "PNG")

        resp = openai_client.images.edit(
            model="gpt-image-1",
            image=("photo.png", buf.getvalue(), "image/png"),
            mask=("mask.png", build_edit_mask(cut.mask), "image/png"),
            prompt=background_prompt(niche),
            size=size,
        )
        raw = base64.b64decode(resp.data[0].b64_json)
        arr = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)

        ok, drift = verify_subject_unchanged(img, arr, cut.mask)
        if not ok:
            out, rep = restage_local(img)
            rep["fallback_from"] = f"generative: товар поплыл, дрейф {drift}"
            return out, rep

        return arr, {"restaged": True, "mode": "generative", "drift": drift}

    except Exception as e:
        out, rep = restage_local(img)
        rep["fallback_from"] = f"generative: {type(e).__name__}: {e}"
        return out, rep


# ─────────────────────────────────────────────────────────────────────────────
# 4. ТОЧКА ВХОДА
# ─────────────────────────────────────────────────────────────────────────────

def restage(photo_path: str, niche: str = "", mode: str = "auto",
            openai_client=None) -> tuple:
    """mode: local | generative | auto (generative с фолбэком на local)"""
    img = cv2.imread(photo_path)
    if img is None:
        raise FileNotFoundError(photo_path)
    img = po.auto_white_balance(img)

    if mode == "local" or openai_client is None:
        return restage_local(img)
    return restage_generative(img, niche, openai_client)
