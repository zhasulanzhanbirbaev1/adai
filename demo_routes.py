"""
demo_routes.py — демо-режим для показа жюри.

ПРИНЦИП: ничего не трогаем. Только добавляем.
Ни один существующий эндпоинт, ни одна таблица, ни app.html не меняются.
Если демо упадёт — основной продукт этого не заметит.

ПОДКЛЮЧЕНИЕ — одна строка в webhook_server.py, рядом с другими роутерами:

    from demo_routes import demo_router
    app.include_router(demo_router)

Интерфейс — пункт «Демо» в app.html. Здесь только эндпоинты.

ЧТО ДЕЛАЕТ:
  - три поля: ниша, оффер, город
  - генерирует баннеры тем же кодом, что и основной продукт
  - НЕ требует Facebook, НЕ пишет в БД, НЕ списывает генерации
  - интерфейс живёт в app.html (пункт «Демо»), здесь только API
"""

from __future__ import annotations

import asyncio
import base64
import os
import time
from collections import defaultdict

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

demo_router = APIRouter(prefix="/demo", tags=["demo"])

# ─────────────────────────────────────────────────────────────────────
# ЛИМИТЫ — защита баланса OpenAI
# ─────────────────────────────────────────────────────────────────────
# При балансе 5,75 $ и цене около 0,22 $ за генерацию хватает примерно
# на 26 прогонов. После выступления ссылку могут разослать по чату
# программы, поэтому потолок обязателен.

MAX_PER_IP = int(os.getenv("DEMO_MAX_PER_IP", "1"))
MAX_TOTAL = int(os.getenv("DEMO_MAX_TOTAL", "20"))

_used_by_ip: dict = defaultdict(int)
_total_used = 0
_started = time.time()


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() if fwd else (
        request.client.host if request.client else "unknown")


# ─────────────────────────────────────────────────────────────────────
# ГЕНЕРАЦИЯ — вызывает тот же пайплайн, что и основной продукт.
# НЕ вызывает: can_generate, increment_generations, Facebook.
# ─────────────────────────────────────────────────────────────────────

async def _generate(niche: str, offer: str, city: str) -> list:
    """Возвращает список из 1-3 элементов:
       [{"image": "data:image/jpeg;base64,...", "headline": "...", "cta": "..."}, ...]
    """
    from image_generator import generate_3_creatives_concept, generate_image
    from banner_composer import compose_creative_banner

    brief = {
        "niche":           niche,
        "geo":             city or "Казахстан",
        "description":     offer,
        "offers":          offer,
        "audience":        "",
        "utp":             "",
        "whatsapp_number": "",
        "client_photo":    False,
    }

    concepts_data = await generate_3_creatives_concept(brief)
    variants = concepts_data.get("variants", [])[:3]

    if not variants:
        missing   = concepts_data.get("missing", [])
        questions = concepts_data.get("questions", [])
        detail = ("Заполните подробнее: " + "; ".join(questions or missing)
                  if (missing or questions) else "Укажите нишу и попробуйте снова")
        raise ValueError(detail)

    async def _one(v: dict) -> dict | None:
        import logging
        from fastapi.concurrency import run_in_threadpool
        try:
            img_bytes    = await generate_image(v["image_prompt_en"], size="1024x1536")
            banner_bytes = await run_in_threadpool(
                compose_creative_banner,
                img_bytes,
                v.get("text_overlay", {}),
                v.get("color_scheme", {}),
                v.get("font_style", "bold_sans"),
            )
            b64 = base64.b64encode(banner_bytes).decode()
            to  = v.get("text_overlay", {})
            return {
                "image":    f"data:image/jpeg;base64,{b64}",
                "headline": to.get("hook_headline", v.get("variant_name", "")),
                "cta":      to.get("cta_button", "Узнать подробнее"),
            }
        except Exception as exc:
            logging.getLogger(__name__).error("Demo banner error: %s", exc)
            return None

    results = await asyncio.gather(*[_one(v) for v in variants])
    banners  = [r for r in results if r is not None]

    if not banners:
        raise RuntimeError("Не удалось создать баннеры — попробуйте ещё раз")

    return banners


# ─────────────────────────────────────────────────────────────────────
# ЭНДПОИНТЫ
# ─────────────────────────────────────────────────────────────────────


@demo_router.post("/generate")
async def demo_generate(request: Request):
    global _total_used

    ip = _client_ip(request)

    if _total_used >= MAX_TOTAL:
        return JSONResponse(
            {"error": "Демо-лимит на сегодня исчерпан. "
                      "Напишите нам — покажем полную версию."},
            status_code=429)

    if _used_by_ip[ip] >= MAX_PER_IP:
        return JSONResponse(
            {"error": "Вы уже сгенерировали демо-баннеры. "
                      "Полная версия доступна после подключения аккаунта."},
            status_code=429)

    body  = await request.json()
    niche = (body.get("niche") or "").strip()[:80]
    offer = (body.get("offer") or "").strip()[:160]
    city  = (body.get("city") or "").strip()[:40]

    if not niche or not offer:
        return JSONResponse(
            {"error": "Заполните нишу и предложение"}, status_code=400)

    # считаем ДО генерации: иначе при параллельных запросах лимит протечёт
    _used_by_ip[ip] += 1
    _total_used += 1

    try:
        variants = await _generate(niche, offer, city)
        return {"ok": True, "variants": variants,
                "left": max(MAX_TOTAL - _total_used, 0)}
    except Exception as e:
        # откатываем счётчик: неудачная генерация не должна съедать лимит
        _used_by_ip[ip] -= 1
        _total_used -= 1
        return JSONResponse(
            {"error": "Не получилось сгенерировать. Попробуйте ещё раз.",
             "detail": type(e).__name__},
            status_code=500)


@demo_router.get("/stats")
async def demo_stats():
    """Открыть перед выступлением, чтобы видеть остаток."""
    return {"total_used": _total_used, "max_total": MAX_TOTAL,
            "left": max(MAX_TOTAL - _total_used, 0),
            "unique_ips": len(_used_by_ip),
            "uptime_min": round((time.time() - _started) / 60, 1)}
