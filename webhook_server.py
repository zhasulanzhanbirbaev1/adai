import os
import asyncio
import logging
import httpx
from fastapi import FastAPI, Request, HTTPException, Header, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse, RedirectResponse
from dotenv import load_dotenv

from database import (
    activate_subscription, get_user, PLANS,
    get_campaigns, create_campaign, toggle_campaign,
    get_fb_token, save_fb_token,
    get_user_stats_summary, get_ai_log, get_today_ai_log,
    get_active_subscription, is_trial_active, update_user_settings,
    get_campaign_stats,
    create_direction, get_directions, get_direction, update_direction,
    add_direction_creative, get_direction_creatives,
    create_agent, get_agent, get_agents, update_agent,
    get_agent_conversations, get_conversation_detail,
    can_generate, increment_generations, generations_left, FREE_GENERATIONS,
    save_user_page_id,
    save_banner_history, get_banner_history, get_banner_history_image,
)
load_dotenv()
BOT_TOKEN     = os.getenv("BOT_TOKEN", "")
ADMIN_KEY     = os.getenv("ADMIN_KEY", "changeme")
TG_API        = f"https://api.telegram.org/bot{BOT_TOKEN}"
FB_APP_ID     = os.getenv("FB_APP_ID", "")
FB_APP_SECRET = os.getenv("FB_APP_SECRET", "")
_BASE_URL     = os.getenv("BASE_URL", "https://like-ai-production.up.railway.app").rstrip("/")
FB_REDIRECT   = f"{_BASE_URL}/fb/callback"

logger = logging.getLogger(__name__)

_bot_app = None


def set_bot_app(application):
    global _bot_app
    _bot_app = application


from contextlib import asynccontextmanager

@asynccontextmanager
async def _lifespan(app):
    """Start bot + scheduler inside FastAPI lifespan so they run with the server."""
    import os as _os
    _base_url = _os.getenv("BASE_URL", "").rstrip("/")
    try:
        from database import init_db
        from bot import build_app
        from ai_manager import build_scheduler
        init_db()
        bot = build_app()
        set_bot_app(bot)
        await bot.initialize()
        await bot.start()
        sched = build_scheduler(bot.bot)
        sched.start()
        if _base_url:
            await bot.bot.set_webhook(
                f"{_base_url}/webhook",
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query", "inline_query"],
            )
            logger.info("Webhook registered: %s/webhook", _base_url)
        logger.info("Bot + scheduler ready")
    except Exception as exc:
        logger.error("Bot startup failed (server still runs): %s", exc, exc_info=True)
        sched = None
        bot = None

    yield

    try:
        if sched:
            sched.shutdown(wait=False)
        if bot:
            await bot.bot.delete_webhook()
            await bot.stop()
            await bot.shutdown()
    except Exception:
        pass


app = FastAPI(title="Adai API", docs_url="/docs", redoc_url=None, lifespan=_lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Temporary in-memory cache for banner file downloads (token → (bytes, label))
import hashlib as _hashlib, time as _time
_BANNER_CACHE: dict = {}  # token -> (img_bytes, label, expires_at)


@app.exception_handler(Exception)
async def _global_exc(request: Request, exc: Exception):
    import traceback
    logger.error("Unhandled %s at %s: %s\n%s", type(exc).__name__, request.url.path, exc, traceback.format_exc())
    return JSONResponse(status_code=500, content={"detail": f"Внутренняя ошибка: {type(exc).__name__}"})


@app.post("/webhook")
async def telegram_webhook(request: Request):
    if _bot_app is None:
        return JSONResponse(status_code=503, content={"ok": False, "error": "bot not ready"})
    from telegram import Update
    data = await request.json()
    update = Update.de_json(data, _bot_app.bot)
    await _bot_app.process_update(update)
    return {"ok": True}


async def _notify(user_id: int, text: str):
    async with httpx.AsyncClient(timeout=8) as client:
        try:
            await client.post(f"{TG_API}/sendMessage",
                              json={"chat_id": user_id, "text": text, "parse_mode": "Markdown"})
        except Exception as e:
            logger.error("TG notify failed: %s", e)


async def _notify_webapp(user_id: int, text: str):
    """Send Telegram notification with a WebApp button to open the Mini App."""
    webapp_url = f"{_BASE_URL}/app?user_id={user_id}"
    async with httpx.AsyncClient(timeout=8) as client:
        try:
            await client.post(f"{TG_API}/sendMessage", json={
                "chat_id": user_id,
                "text": text,
                "parse_mode": "Markdown",
                "reply_markup": {
                    "inline_keyboard": [[
                        {"text": "📊 Открыть кабинет", "web_app": {"url": webapp_url}}
                    ]]
                }
            })
        except Exception as e:
            logger.error("TG webapp notify failed: %s", e)


async def _notify_photo(user_id: int, img_bytes: bytes, caption: str = ""):
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            await client.post(
                f"{TG_API}/sendPhoto",
                data={"chat_id": user_id, "caption": caption},
                files={"photo": ("banner.jpg", img_bytes, "image/jpeg")},
            )
        except Exception as e:
            logger.error("TG photo notify failed: %s", e)


def _get_uid(user_id: int = Query(..., description="Telegram user ID")) -> int:
    if not get_user(user_id):
        raise HTTPException(404, "User not found")
    return user_id


# в"Ђв"Ђ Health / App в"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђ

@app.get("/")
async def landing():
    return FileResponse(os.path.join(os.path.dirname(__file__), "landing.html"))

@app.get("/health")
async def health():
    return {"status": "ok", "service": "Adai"}


@app.api_route("/app", methods=["GET", "HEAD"])
async def serve_app():
    return FileResponse(os.path.join(os.path.dirname(__file__), "app.html"))

@app.get("/privacy")
async def serve_privacy():
    return FileResponse(os.path.join(os.path.dirname(__file__), "privacy.html"))

@app.get("/terms")
async def serve_terms():
    return FileResponse(os.path.join(os.path.dirname(__file__), "terms.html"))


# в"Ђв"Ђ Manual Activation в"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђ

def _check_admin(x_admin_key: str = Header(None, alias="X-Admin-Key")):
    if x_admin_key != ADMIN_KEY:
        raise HTTPException(403, "Forbidden")


@app.post("/admin/reset-generations", dependencies=[Depends(_check_admin)])
async def admin_reset_generations(request: Request):
    body = await request.json()
    uid  = int(body.get("user_id", 0))
    if not uid:
        raise HTTPException(400, "user_id required")
    from database import get_conn
    with get_conn() as conn:
        conn.execute("UPDATE users SET generations_used = 0 WHERE id = %s", (uid,))
    return {"status": "ok", "user_id": uid, "generations_used": 0}


@app.post("/admin/activate", dependencies=[Depends(_check_admin)])
async def admin_activate(request: Request):
    body = await request.json()
    uid  = body.get("user_id")
    plan = body.get("plan")
    if not uid or not plan:
        raise HTTPException(400, "user_id and plan required")
    if plan not in PLANS:
        raise HTTPException(400, f"Unknown plan: {plan}")
    if not get_user(int(uid)):
        raise HTTPException(404, "User not found")
    activate_subscription(int(uid), plan, f"manual-{uid}")
    await _notify(int(uid), f"✅ *Подписка активирована*\n\nПериод: *{PLANS[plan]['name']}*")
    return {"status": "ok"}


# в"Ђв"Ђ Dashboard API в"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђ

@app.get("/api/dashboard")
async def api_dashboard(user_id: int = Depends(_get_uid)):
    summary  = get_user_stats_summary(user_id, days=30)
    camps    = get_campaigns(user_id)
    ai_today = get_today_ai_log(user_id)
    sub      = get_active_subscription(user_id)

    camp_list = []
    for c in camps[:5]:
        stats = get_campaign_stats(c["id"], days=7)
        total_imp = sum(s["impressions"] for s in stats)
        total_cl  = sum(s["clicks"] for s in stats)
        ctr = total_cl / total_imp * 100 if total_imp > 0 else 0
        camp_list.append({
            "id": c["id"], "name": c["name"], "active": bool(c["active"]),
            "budget": c["budget"], "ctr": round(ctr, 2),
            "paused_by_ai": bool(c["paused_by_ai"]),
            "ai_scenario": c["ai_scenario"],
        })

    full_log = get_ai_log(user_id, limit=500)
    # Saved = daily budget of campaigns paused by AI (approximate)
    ai_saved = sum(
        c.get("budget", 0) for c in camps if c.get("paused_by_ai")
    ) * 3  # estimate: saved 3 days of wasted spend

    return {
        "stats": summary,
        "campaigns": camp_list,
        "campaigns_managed": len([c for c in camps if c.get("active") or c.get("paused_by_ai")]),
        "ai_saved": round(ai_saved),
        "ai_decisions_count": len(full_log),
        "ai_today": [
            {"scenario": r["scenario"], "decision": r["decision"],
             "campaign": r["campaign_name"], "created_at": r["created_at"]}
            for r in ai_today
        ],
        "subscription": {
            "active": sub is not None or is_trial_active(user_id),
            "plan": sub["plan"] if sub else "trial",
            "expires": sub["expires_at"][:10] if sub else None,
        },
    }


# в"Ђв"Ђ Campaigns API в"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђ

@app.get("/api/campaigns")
async def api_campaigns(user_id: int = Depends(_get_uid)):
    camps = get_campaigns(user_id)
    result = []
    for c in camps:
        stats = get_campaign_stats(c["id"], days=7)
        imp = sum(s["impressions"] for s in stats)
        cl  = sum(s["clicks"] for s in stats)
        lds = sum(s["leads"] for s in stats)
        spn = sum(s["spent"] for s in stats)
        ctr = cl / imp * 100 if imp > 0 else 0
        cpl = spn / lds if lds > 0 else 0
        result.append({
            "id": c["id"], "name": c["name"], "type": c["type"],
            "goal": c["goal"], "geo": c["geo"], "budget": c["budget"],
            "active": bool(c["active"]), "paused_by_ai": bool(c["paused_by_ai"]),
            "ai_scenario": c["ai_scenario"], "created_at": c["created_at"],
            "stats": {"impressions": imp, "clicks": cl, "leads": lds,
                      "spent": spn, "ctr": round(ctr, 2), "cpl": round(cpl, 0)},
        })
    return result


@app.post("/api/campaigns")
async def api_create_campaign(request: Request, user_id: int = Depends(_get_uid)):
    sub = get_active_subscription(user_id)
    plan_key = sub["plan"] if sub else ("trial" if is_trial_active(user_id) else None)
    plan_info = PLANS.get(plan_key, {})
    limit = plan_info.get("campaign_limit")
    if limit is not None:
        existing = get_campaigns(user_id)
        if len(existing) >= limit:
            raise HTTPException(403, f"На тарифе «1 месяц» доступен {limit} рекламный кабинет. Повысьте тариф для добавления.")
    body = await request.json()
    cid = create_campaign(
        user_id,
        name=body.get("name", "Новая кампания"),
        camp_type=body.get("type", "photo"),
        goal=body.get("goal", "whatsapp"),
        geo=body.get("geo", "Алматы"),
        budget=float(body.get("budget", 0)),
        target_cpl=float(body.get("target_cpl", 0)),
    )
    return {"id": cid, "status": "created"}


@app.patch("/api/campaigns/{campaign_id}/toggle")
async def api_toggle(campaign_id: int, user_id: int = Depends(_get_uid)):
    new_state = toggle_campaign(campaign_id, user_id)
    return {"active": new_state}


# в"Ђв"Ђ Analytics API в"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђ

@app.get("/api/analytics")
async def api_analytics(user_id: int = Depends(_get_uid), period: str = "30"):
    days = {"7": 7, "30": 30, "1": 1}.get(period, 30)
    summary = get_user_stats_summary(user_id, days=days)
    camps   = get_campaigns(user_id)
    table   = []
    for c in camps:
        stats = get_campaign_stats(c["id"], days=days)
        imp = sum(s["impressions"] for s in stats)
        cl  = sum(s["clicks"] for s in stats)
        lds = sum(s["leads"] for s in stats)
        spn = sum(s["spent"] for s in stats)
        table.append({
            "name": c["name"],
            "impressions": imp, "clicks": cl, "leads": lds, "spent": spn,
            "ctr": round(cl / imp * 100, 2) if imp else 0,
            "cpl": round(spn / lds, 0) if lds else 0,
        })
    return {"summary": summary, "table": table}


# в"Ђв"Ђ AI Log API в"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђ

@app.get("/api/ai-log")
async def api_ai_log(user_id: int = Depends(_get_uid), limit: int = Query(50)):
    log = get_ai_log(user_id, limit=min(limit, 200))
    return [
        {"id": r.get("id", i), "scenario": r["scenario"],
         "decision": r["decision"], "campaign": r["campaign_name"],
         "created_at": r["created_at"]}
        for i, r in enumerate(log)
    ]


# в"Ђв"Ђ Settings API в"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђ

@app.get("/api/settings")
async def api_settings(user_id: int = Depends(_get_uid)):
    user = get_user(user_id)
    fb   = get_fb_token(user_id)
    sub  = get_active_subscription(user_id)

    instagram = None
    if fb:
        try:
            async with httpx.AsyncClient(timeout=6) as client:
                r = await client.get(
                    "https://graph.facebook.com/v19.0/me/accounts",
                    params={
                        "access_token": fb["access_token"],
                        "fields": "id,name,instagram_business_account{id,username,profile_picture_url}",
                    },
                )
                pages = r.json().get("data", [])
                for page in pages:
                    ig = page.get("instagram_business_account")
                    if ig:
                        instagram = {
                            "username": ig.get("username"),
                            "profile_picture_url": ig.get("profile_picture_url"),
                            "page_name": page.get("name"),
                        }
                        break
        except Exception:
            pass

    return {
        "user": {"id": user["id"], "first_name": user["first_name"],
                 "username": user["username"], "target_cpl": user["target_cpl"],
                 "whatsapp": user["whatsapp"],
                 "fb_page_id": user.get("fb_page_id", "")},
        "facebook": {"connected": fb is not None,
                     "ad_account_id": fb["ad_account_id"] if fb else None,
                     "connected_at": fb["connected_at"][:10] if fb else None},
        "instagram": instagram,
        "subscription": {"active": sub is not None or is_trial_active(user_id),
                         "plan": sub["plan"] if sub else "trial",
                         "expires": sub["expires_at"][:10] if sub else None,
                         "trial_ends": user["trial_ends_at"][:10] if user["trial_ends_at"] else None},
        "generations": {"used": user.get("generations_used", 0), "free": FREE_GENERATIONS,
                        "left": generations_left(user_id)},
    }


@app.get("/api/fb/pages")
async def api_fb_pages(user_id: int = Depends(_get_uid)):
    fb = get_fb_token(user_id)
    if not fb:
        raise HTTPException(400, "Facebook not connected")
    from fb_launcher import get_fb_pages
    pages = get_fb_pages(fb["access_token"])
    return {"pages": pages}


@app.post("/api/studio/launch")
async def api_studio_launch(request: Request, user_id: int = Depends(_get_uid)):
    import base64 as b64mod
    fb = get_fb_token(user_id)
    if not fb:
        raise HTTPException(400, "Facebook не подключён. Подключите в Настройках.")

    body          = await request.json()
    image_b64     = body.get("image_base64", "")
    ad_text       = body.get("ad_text", "").strip()
    budget_kzt    = float(body.get("budget_kzt", 5000))
    whatsapp      = body.get("whatsapp_number", "").strip()
    page_id       = body.get("page_id", "").strip()
    campaign_name = body.get("campaign_name", "Adai кампания").strip()
    age_min       = int(body.get("age_min", 20))
    age_max       = int(body.get("age_max", 55))
    gender        = body.get("gender", "all")

    if not image_b64:
        raise HTTPException(400, "image_base64 required")
    if not page_id:
        raise HTTPException(400, "page_id required — укажите ID страницы Facebook в Настройках")

    from fb_launcher import upload_image_to_fb, create_fb_campaign, create_fb_adset, create_fb_ad

    try:
        img_bytes  = b64mod.b64decode(image_b64.split(",")[-1])
        image_hash = upload_image_to_fb(fb["access_token"], fb["ad_account_id"], img_bytes, "banner.jpg")
    except Exception as e:
        logger.error("Image upload error: %s", e)
        raise HTTPException(500, f"Ошибка загрузки изображения: {str(e)}")

    try:
        camp_id  = create_fb_campaign(fb["access_token"], fb["ad_account_id"], name=campaign_name)
        adset_id = create_fb_adset(
            fb["access_token"], fb["ad_account_id"], camp_id,
            name=f"{campaign_name} AdSet",
            daily_budget_kzt=budget_kzt,
            geo="KZ", age_min=age_min, age_max=age_max,
            gender=gender, whatsapp_number=whatsapp,
        )
        ad_id = create_fb_ad(
            fb["access_token"], fb["ad_account_id"], adset_id,
            name=f"{campaign_name} Ad",
            image_hash=image_hash,
            ad_text=ad_text or campaign_name,
            page_id=page_id,
            whatsapp_number=whatsapp,
        )
    except Exception as e:
        logger.error("Campaign launch error: %s", e)
        raise HTTPException(500, f"Ошибка запуска: {str(e)}")

    await _notify(user_id,
        f"🚀 *Кампания запущена!*\n\n"
        f"📌 {campaign_name}\n"
        f"💰 Бюджет: {int(budget_kzt):,} ₸/день\n"
        f"🆔 ID: `{camp_id}`\n\n"
        f"Статус: на проверке Facebook")

    return {"campaign_id": camp_id, "adset_id": adset_id, "ad_id": ad_id, "status": "launched"}


@app.get("/api/facebook/pages")
async def api_facebook_pages(user_id: int = Depends(_get_uid)):
    """Fetch user's Facebook Pages using saved token."""
    fb = get_fb_token(user_id)
    if not fb or not fb.get("access_token"):
        raise HTTPException(400, "Facebook не подключён")
    token = fb["access_token"]
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get("https://graph.facebook.com/v19.0/me/accounts", params={
            "access_token": token,
            "fields": "id,name,category,fan_count",
        })
    data = r.json()
    if "error" in data:
        raise HTTPException(400, data["error"].get("message", "Ошибка Facebook"))
    pages = data.get("data", [])
    return {
        "pages": pages,
        "ad_account_id": fb.get("ad_account_id", ""),
        "connected": True,
    }


@app.put("/api/settings/facebook")
async def api_save_facebook(request: Request, user_id: int = Depends(_get_uid)):
    body = await request.json()
    token = body.get("access_token")
    acct  = body.get("ad_account_id")
    if not token or not acct:
        raise HTTPException(400, "access_token and ad_account_id required")
    save_fb_token(user_id, token, acct)
    return {"status": "saved"}


@app.put("/api/settings/profile")
async def api_save_profile(request: Request, user_id: int = Depends(_get_uid)):
    body = await request.json()
    update_user_settings(
        user_id,
        target_cpl=body.get("target_cpl"),
        whatsapp=body.get("whatsapp"),
    )
    if body.get("fb_page_id"):
        save_user_page_id(user_id, body["fb_page_id"])
    return {"status": "saved"}


# в"Ђв"Ђ Facebook OAuth в"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђ

_FB_SUCCESS_TMPL = """<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>*{box-sizing:border-box}body{font-family:-apple-system,sans-serif;background:#030712;color:#fff;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;padding:16px}.card{background:#0f172a;border:1px solid #1e293b;border-radius:20px;padding:40px 32px;text-align:center;max-width:400px;width:100%}.icon{font-size:64px;margin-bottom:16px}.title{font-size:24px;font-weight:700;margin-bottom:10px}.sub{color:#64748b;font-size:15px;line-height:1.7;margin-bottom:28px}.btn{display:block;background:linear-gradient(135deg,#2481cc,#1a6aad);color:#fff;font-weight:700;font-size:16px;padding:16px 28px;border-radius:14px;text-decoration:none;transition:opacity .2s}.btn:hover{opacity:.9}.hint{margin-top:16px;font-size:12px;color:#374151}</style>
<script>
  // Try to open Telegram automatically on mobile
  setTimeout(function(){
    try { window.location.href = 'https://t.me/zhasclaude_bot'; } catch(e){}
  }, 1800);
</script>
</head>
<body><div class="card">
  <div class="icon">✅</div>
  <div class="title">Facebook подключён!</div>
  <div class="sub">Кампании синхронизированы.<br>Telegram уже прислал уведомление — откройте его и нажмите <b>«Открыть кабинет»</b>.</div>
  <a class="btn" href="https://t.me/zhasclaude_bot">Вернуться в Telegram →</a>
  <div class="hint">Страница автоматически перейдёт через 2 секунды</div>
</div></body></html>"""

_FB_ERROR = """<!DOCTYPE html><html><head><meta charset="utf-8">
<style>*{{box-sizing:border-box}}body{{font-family:-apple-system,sans-serif;background:#030712;color:#fff;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}}.card{{background:#0f172a;border:1px solid #1e293b;border-radius:16px;padding:40px;text-align:center;max-width:400px}}.icon{{font-size:56px;margin-bottom:16px}}.title{{font-size:22px;font-weight:700;margin-bottom:8px}}.sub{{color:#64748b;font-size:15px}}</style></head>
<body><div class="card"><div class="icon">вќЊ</div><div class="title">{title}</div><div class="sub">{msg}</div></div></body></html>"""


@app.get("/fb/connect")
async def fb_connect(user_id: int = Query(...)):
    if not get_user(user_id):
        raise HTTPException(404, "User not found")
    if not FB_APP_ID:
        raise HTTPException(503, "Facebook App not configured")
    from urllib.parse import urlencode
    params = urlencode({
        "client_id": FB_APP_ID,
        "redirect_uri": FB_REDIRECT,
        "scope": "ads_management,ads_read,business_management,pages_show_list",
        "state": str(user_id),
        "response_type": "code",
    })
    return RedirectResponse(f"https://www.facebook.com/v19.0/dialog/oauth?{params}")


@app.get("/fb/callback")
async def fb_callback(code: str = Query(None), state: str = Query(None),
                      error: str = Query(None), error_description: str = Query(None)):
    if error:
        return HTMLResponse(_FB_ERROR.format(title="Отмена", msg="Вы отменили подключение Facebook."))
    if not code or not state:
        return HTMLResponse(_FB_ERROR.format(title="Ошибка", msg="Неверный запрос."))

    try:
        user_id = int(state)
    except ValueError:
        return HTMLResponse(_FB_ERROR.format(title="Ошибка", msg="Неверный state."))

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get("https://graph.facebook.com/v19.0/oauth/access_token", params={
            "client_id": FB_APP_ID, "client_secret": FB_APP_SECRET,
            "redirect_uri": FB_REDIRECT, "code": code,
        })
        token_data = r.json()

    if "error" in token_data:
        msg = token_data["error"].get("message", "Ошибка Facebook")
        return HTMLResponse(_FB_ERROR.format(title="Ошибка Facebook", msg=msg))

    short_token = token_data["access_token"]

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get("https://graph.facebook.com/v19.0/oauth/access_token", params={
            "grant_type": "fb_exchange_token", "client_id": FB_APP_ID,
            "client_secret": FB_APP_SECRET, "fb_exchange_token": short_token,
        })
        ll = r.json()
    long_token = ll.get("access_token", short_token)

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get("https://graph.facebook.com/v19.0/me/adaccounts", params={
            "access_token": long_token, "fields": "id,name,account_status",
        })
        accounts = r.json().get("data", [])

    if not accounts:
        return HTMLResponse(_FB_ERROR.format(title="Аккаунты не найдены",
                            msg="Рекламные аккаунты Facebook не найдены."))

    if len(accounts) == 1:
        ad_account_id = accounts[0]["id"]
        save_fb_token(user_id, long_token, ad_account_id)
    else:
        items = "".join(
            f'<a href="/fb/select?user_id={user_id}&token={long_token}&account_id={a["id"]}" '
            f'style="display:block;background:#1e293b;border:1px solid #334155;border-radius:10px;'
            f'padding:16px;margin:8px 0;text-decoration:none;color:#fff;font-size:15px">'
            f'<b>{a["name"]}</b><br><span style="color:#64748b;font-size:13px">{a["id"]}</span></a>'
            for a in accounts
        )
        return HTMLResponse(f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>*{{box-sizing:border-box}}body{{font-family:-apple-system,sans-serif;background:#030712;color:#fff;padding:24px 20px;max-width:480px;margin:0 auto}}h2{{font-size:20px;margin-bottom:6px}}p{{color:#64748b;font-size:14px;margin-bottom:20px}}</style></head>
<body>
<h2>Выберите рекламный аккаунт</h2>
<p>Выберите аккаунт Facebook Ads для подключения к Adai</p>
{items}
</body></html>""")

    from ai_manager import sync_fb_campaigns
    import asyncio
    count = await asyncio.get_event_loop().run_in_executor(
        None, sync_fb_campaigns, user_id, long_token, ad_account_id
    )
    sync_text = f"📊 Синхронизировано кампаний: *{count}*" if count > 0 else "📊 Активных кампаний не найдено"

    await _notify_webapp(user_id,
        f"✅ *Facebook подключён и синхронизирован!*\n\n"
        f"Аккаунт: `{ad_account_id}`\n"
        f"{sync_text}\n\n"
        f"Нажмите кнопку ниже чтобы открыть кабинет 👇")
    return HTMLResponse(_FB_SUCCESS_TMPL)


@app.get("/fb/select")
async def fb_select(user_id: int = Query(...), token: str = Query(...), account_id: str = Query(...)):
    save_fb_token(user_id, token, account_id)
    from ai_manager import sync_fb_campaigns
    count = await asyncio.get_event_loop().run_in_executor(
        None, sync_fb_campaigns, user_id, token, account_id
    )
    sync_text = f"📊 Синхронизировано кампаний: *{count}*" if count > 0 else "📊 Активных кампаний не найдено"
    await _notify_webapp(user_id,
        f"✅ *Facebook подключён!*\n\nАккаунт: `{account_id}`\n{sync_text}\n\n"
        f"Нажмите кнопку ниже чтобы открыть кабинет 👇")
    return HTMLResponse(_FB_SUCCESS_TMPL)


# в"Ђв"Ђ Directions API в"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђ

@app.get("/api/directions")
async def api_get_directions(user_id: int = Depends(_get_uid)):
    dirs = get_directions(user_id)
    result = []
    for d in dirs:
        creatives = get_direction_creatives(d["id"])
        result.append({**dict(d), "creatives_count": len(creatives)})
    return result


@app.post("/api/directions")
async def api_create_direction(request: Request, user_id: int = Depends(_get_uid)):
    body = await request.json()
    name = body.get("name", "Новое направление")
    did = create_direction(user_id, name)
    fields = {k: v for k, v in body.items()
              if k in ("niche","description","utp","audience","pains","offers",
                       "geo","gender","traffic_dest","whatsapp_number",
                       "daily_budget","target_cpl","welcome_message","pre_message")}
    if fields:
        update_direction(did, **fields)
    return {"id": did, "status": "created"}


@app.get("/api/directions/{did}")
async def api_get_direction(did: int, user_id: int = Depends(_get_uid)):
    d = get_direction(did, user_id)
    if not d:
        raise HTTPException(404, "Direction not found")
    creatives = get_direction_creatives(did)
    return {**dict(d), "creatives": [dict(c) for c in creatives]}


@app.put("/api/directions/{did}")
async def api_update_direction(did: int, request: Request, user_id: int = Depends(_get_uid)):
    if not get_direction(did, user_id):
        raise HTTPException(404, "Direction not found")
    body = await request.json()
    fields = {k: v for k, v in body.items()
              if k in ("name","niche","description","utp","audience","pains","offers",
                       "geo","gender","traffic_dest","whatsapp_number",
                       "daily_budget","target_cpl","welcome_message","pre_message","ad_text")}
    if fields:
        update_direction(did, **fields)
    return {"status": "updated"}


@app.post("/api/directions/{did}/generate-strategy")
async def api_generate_strategy(did: int, user_id: int = Depends(_get_uid)):
    d = get_direction(did, user_id)
    if not d:
        raise HTTPException(404, "Direction not found")
    from fb_launcher import generate_brief_strategy
    strategy = await generate_brief_strategy(dict(d))
    update_direction(did, ad_text=strategy["ad_texts"]["urgent"], status="brief_ready")
    return strategy


@app.post("/api/directions/{did}/upload-creative")
async def api_upload_creative(did: int, request: Request, user_id: int = Depends(_get_uid)):
    import base64 as b64mod
    d = get_direction(did, user_id)
    if not d:
        raise HTTPException(404, "Direction not found")
    fb = get_fb_token(user_id)
    if not fb:
        raise HTTPException(400, "Facebook not connected")
    body = await request.json()
    image_b64 = body.get("image_base64", "")
    filename = body.get("filename", "creative.jpg")
    if not image_b64:
        raise HTTPException(400, "image_base64 required")
    img_bytes = b64mod.b64decode(image_b64)
    from fb_launcher import upload_image_to_fb
    img_hash = upload_image_to_fb(fb["access_token"], fb["ad_account_id"], img_bytes, filename)
    cid = add_direction_creative(did, filename=filename, fb_image_hash=img_hash)
    return {"id": cid, "fb_image_hash": img_hash}


@app.post("/api/directions/{did}/launch")
async def api_launch_direction(did: int, request: Request, user_id: int = Depends(_get_uid)):
    d = get_direction(did, user_id)
    if not d:
        raise HTTPException(404, "Direction not found")
    fb = get_fb_token(user_id)
    if not fb:
        raise HTTPException(400, "Facebook not connected")
    creatives = get_direction_creatives(did)
    if not creatives:
        raise HTTPException(400, "Загрузите хотя бы один креатив")
    body = await request.json()
    ad_text = body.get("ad_text") or d["ad_text"] or d["description"] or "Свяжитесь с нами"
    page_id = body.get("page_id", "")
    if not page_id:
        raise HTTPException(400, "page_id required")

    from fb_launcher import create_fb_campaign, create_fb_adset, create_fb_ad, generate_brief_strategy
    strategy = await generate_brief_strategy(dict(d))

    camp_id = create_fb_campaign(
        fb["access_token"], fb["ad_account_id"],
        name=f"{d['name']} | Adai",
    )
    adset_id = create_fb_adset(
        fb["access_token"], fb["ad_account_id"], camp_id,
        name=f"{d['name']} AdSet",
        daily_budget_kzt=d["daily_budget"] or 5000,
        geo=d["geo"] or "Казахстан",
        age_min=strategy.get("age_min", 20),
        age_max=strategy.get("age_max", 45),
        gender=d["gender"] or "all",
        whatsapp_number=d["whatsapp_number"] or "",
    )
    ad_ids = []
    for cr in creatives[:3]:
        if cr["fb_image_hash"]:
            ad_id = create_fb_ad(
                fb["access_token"], fb["ad_account_id"], adset_id,
                name=f"{d['name']} Ad",
                image_hash=cr["fb_image_hash"],
                ad_text=ad_text,
                page_id=page_id,
                whatsapp_number=d["whatsapp_number"] or "",
            )
            ad_ids.append(ad_id)

    update_direction(did, fb_campaign_id=camp_id, status="launched")
    await _notify(user_id,
        f"🚀 *Кампания запущена!*\n\n"
        f"Направление: *{d['name']}*\n"
        f"Кампания: `{camp_id}`\n"
        f"Объявлений: {len(ad_ids)}\n\n"
        f"Статус: на проверке Facebook")
    return {"campaign_id": camp_id, "adset_id": adset_id, "ads": ad_ids, "strategy": strategy}


# в"Ђв"Ђ Image Generator API в"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђ

@app.post("/api/moderate")
async def api_moderate(request: Request, user_id: int = Depends(_get_uid)):
    from image_generator import moderate_ad_content
    body = await request.json()
    text = body.get("text", "")
    if not text:
        return {"status": "approved", "issues": [], "suggestion": ""}
    return await moderate_ad_content(text)


@app.post("/api/audience-suggest")
async def api_audience_suggest(request: Request, user_id: int = Depends(_get_uid)):
    from image_generator import suggest_audience
    body = await request.json()
    result = await suggest_audience(body.get("niche", ""), body.get("offer", ""))
    return result


@app.post("/api/send-banner")
async def api_send_banner(request: Request, user_id: int = Depends(_get_uid)):
    import base64 as b64mod
    body      = await request.json()
    image_b64 = body.get("image_b64", "")
    label     = body.get("label", "Баннер")
    if not image_b64:
        raise HTTPException(400, "image_b64 required")
    if "," in image_b64:
        image_b64 = image_b64.split(",")[1]
    img_bytes = b64mod.b64decode(image_b64)
    caption   = f"🎨 Ваш баннер *{label}*\n📐 1080×1350 — готов для Instagram/Facebook рекламы"
    await _notify_photo(user_id, img_bytes, caption)
    return {"ok": True}


@app.post("/api/banner-url")
async def api_banner_url(request: Request, user_id: int = Depends(_get_uid)):
    """Save banner to temp cache and return a direct download URL."""
    import base64 as b64mod
    body      = await request.json()
    image_b64 = body.get("image_b64", "")
    label     = body.get("label", "banner")
    if not image_b64:
        raise HTTPException(400, "image_b64 required")
    if "," in image_b64:
        image_b64 = image_b64.split(",")[1]
    img_bytes = b64mod.b64decode(image_b64)
    token = _hashlib.md5(f"{user_id}{_time.time()}".encode()).hexdigest()[:16]
    _BANNER_CACHE[token] = (img_bytes, label, _time.time() + 3600)
    # Clean expired entries
    expired = [k for k, v in _BANNER_CACHE.items() if v[2] < _time.time()]
    for k in expired:
        del _BANNER_CACHE[k]
    url = f"{_BASE_URL}/api/banner-file/{token}"
    filename = f"adai-{label.lower().replace(' ', '-')}-1080x1350.jpg"
    return {"url": url, "filename": filename}


@app.get("/api/banner-file/{token}")
async def api_banner_file(token: str):
    """Serve banner as JPEG file for direct download / gallery save."""
    from fastapi.responses import Response
    item = _BANNER_CACHE.get(token)
    if not item or item[2] < _time.time():
        raise HTTPException(404, "Ссылка устарела, сгенерируйте новую")
    img_bytes, label, _ = item
    filename = f"adai-{label.lower().replace(' ', '-')}-1080x1350.jpg"
    return Response(
        content=img_bytes,
        media_type="image/jpeg",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@app.get("/api/history")
async def api_history(user_id: int = Depends(_get_uid)):
    """Return list of past generated banners (no image bytes)."""
    items = get_banner_history(user_id, limit=30)
    return {"items": items}


@app.get("/api/history/{banner_id}/image")
async def api_history_image(banner_id: int, user_id: int = Query(...)):
    """Return banner image as JPEG."""
    from fastapi.responses import Response
    img_b64 = get_banner_history_image(banner_id, user_id)
    if not img_b64:
        raise HTTPException(404, "Баннер не найден")
    import base64 as _bimg
    img_bytes = _bimg.b64decode(img_b64)
    return Response(content=img_bytes, media_type="image/jpeg",
                    headers={"Content-Disposition": "inline; filename=\"banner.jpg\""})


@app.post("/api/generate-banner")
async def api_generate_banner(request: Request, user_id: int = Depends(_get_uid)):
    try:
        import base64 as b64mod
        import asyncio as _asyncio
        from image_generator import (
            generate_dalle_image, generate_instagram_copy,
            generate_3_creatives_concept, suggest_audience, OPENAI_AVAILABLE,
        )
        from banner_composer import compose_creative_banner
    except Exception as e:
        logger.error("Import error in generate-banner: %s", e)
        raise HTTPException(500, f"Import error: {str(e)}")

    if not OPENAI_AVAILABLE:
        raise HTTPException(503, "OpenAI API не настроен")

    try:
        if not can_generate(user_id):
            raise HTTPException(402, f"Бесплатные генерации закончились. Оформите подписку.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("can_generate error: %s", e)

    body        = await request.json()
    niche       = (body.get("niche") or "").strip()
    description = (body.get("description") or body.get("offer") or "").strip()
    audience    = (body.get("audience") or "").strip()
    image_b64   = body.get("image_base64")

    if not niche and not description:
        raise HTTPException(400, "Укажите нишу или оффер")

    # ── Step 1: AI Creative Director generates 3 concepts ──────────────────
    brief = {
        "niche":       niche,
        "geo":         body.get("geo", "Казахстан"),
        "description": description,
        "offers":      description,
        "audience":    audience,
        "utp":         "",
        "pains":       "",
        "whatsapp_number": "",
    }
    try:
        concepts_data = await generate_3_creatives_concept(brief)
        variants      = concepts_data.get("variants", [])[:3]
    except Exception as e:
        logger.error("Creative concept error: %s", e)
        raise HTTPException(500, f"Ошибка AI Creative Director: {str(e)}")

    if not variants:
        raise HTTPException(500, "AI не вернул концепции, попробуйте ещё раз")

    # ── Step 2: Get images (user photo OR generate 3 in parallel) ──────────
    if image_b64:
        # User uploaded their own photo — use it for all 3 variants
        try:
            img_bytes_list = [b64mod.b64decode(image_b64)] * len(variants)
        except Exception as e:
            raise HTTPException(400, f"Неверный формат изображения: {e}")
    else:
        # Generate 3 unique images in parallel (one per concept)
        async def _gen_img(prompt: str):
            try:
                return await generate_dalle_image(prompt, size="1024x1536")
            except Exception as ex:
                logger.error("Image gen error: %s", ex)
                return None

        results = await _asyncio.gather(*[_gen_img(v["image_prompt_en"]) for v in variants])
        img_bytes_list = list(results)

    # ── Step 3: Compose banners ─────────────────────────────────────────────
    banners = []
    all_headlines, all_bullets, first_cta = [], [], ""
    for i, (variant, img_bytes) in enumerate(zip(variants, img_bytes_list)):
        if img_bytes is None:
            continue
        try:
            banner_bytes = compose_creative_banner(
                img_bytes,
                variant.get("text_overlay", {}),
                variant.get("color_scheme", {}),
                variant.get("font_style", "bold_sans"),
            )
            import base64 as _b
            b64 = _b.b64encode(banner_bytes).decode()
            to  = variant.get("text_overlay", {})
            banners.append({
                "label":      variant.get("variant_name", f"Вариант {i+1}"),
                "image":      f"data:image/jpeg;base64,{b64}",
                "size":       "1080×1350",
                "post_copy":  variant.get("post_copy", ""),
                "hashtags":   variant.get("hashtags", []),
                "concept":    variant.get("concept_explanation", ""),
            })
            hl = to.get("hook_headline", "")
            if hl:
                all_headlines.append(hl)
            all_bullets = to.get("bullets") or all_bullets
            if not first_cta:
                first_cta = to.get("cta_button", "")
        except Exception as e:
            logger.error("Banner compose error variant %d: %s", i, e)

    if not banners:
        raise HTTPException(500, "Не удалось создать ни одного баннера")

    # ── Step 4: Instagram copy + audience ──────────────────────────────────
    try:
        insta = await generate_instagram_copy(niche or description, description, audience)
    except Exception:
        # Use post_copy from first variant as fallback
        insta = {"caption": banners[0].get("post_copy", ""),
                 "hashtags": " ".join(banners[0].get("hashtags", []))}

    try:
        aud_sug = await suggest_audience(niche or description, description)
    except Exception:
        aud_sug = {}

    # ── Step 5: Track generation + save history ─────────────────────────────
    left = 9
    try:
        increment_generations(user_id)
        left = generations_left(user_id)
    except Exception as e:
        logger.error("DB generations update error: %s", e)

    try:
        import base64 as _bh
        for banner in banners:
            raw_b64 = banner["image"].split(",", 1)[-1]
            save_banner_history(
                user_id=user_id,
                niche=niche or description or "",
                label=banner.get("label", ""),
                concept=banner.get("concept", ""),
                post_copy=banner.get("post_copy", ""),
                image_b64=raw_b64,
            )
    except Exception as e:
        logger.error("History save error: %s", e)

    return {
        "banners":          banners,
        "copy":             {"headlines": all_headlines, "bullets": all_bullets, "cta": first_cta},
        "instagram":        insta,
        "audience":         aud_sug,
        "generations_left": left,
    }


# в"Ђв"Ђ AI Agents API в"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђв"Ђ

@app.get("/chat/{agent_id}")
async def serve_chat(agent_id: int):
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(404, "Агент не найден")
    return FileResponse(os.path.join(os.path.dirname(__file__), "chat.html"))


@app.get("/api/agents")
async def api_get_agents(user_id: int = Depends(_get_uid)):
    agents = get_agents(user_id)
    result = []
    for a in agents:
        convs = get_agent_conversations(a["id"], limit=1000)
        result.append({
            "id": a["id"], "name": a["name"],
            "system_prompt": a["system_prompt"],
            "greeting": a["greeting"],
            "active": a["active"],
            "created_at": a["created_at"],
            "conversations_count": len(convs),
            "chat_url": f"{_BASE_URL}/chat/{a['id']}",
        })
    return result


@app.post("/api/agents")
async def api_create_agent(request: Request, user_id: int = Depends(_get_uid)):
    body = await request.json()
    name = body.get("name", "Мой ИИ-агент")
    system_prompt = body.get("system_prompt", "Ты вежливый помощник.")
    greeting = body.get("greeting", "Здравствуйте! Чем могу помочь?")
    aid = create_agent(user_id, name, system_prompt, greeting)
    return {"id": aid, "chat_url": f"{_BASE_URL}/chat/{aid}"}


@app.put("/api/agents/{aid}")
async def api_update_agent(aid: int, request: Request, user_id: int = Depends(_get_uid)):
    agent = get_agent(aid)
    if not agent:
        raise HTTPException(404, "Agent not found")
    body = await request.json()
    fields = {k: v for k, v in body.items()
              if k in ("name", "system_prompt", "greeting", "active")}
    if fields:
        update_agent(aid, **fields)
    return {"status": "updated"}


@app.get("/api/agents/{aid}/conversations")
async def api_agent_conversations(aid: int, user_id: int = Depends(_get_uid)):
    agent = get_agent(aid)
    if not agent:
        raise HTTPException(404, "Agent not found")
    convs = get_agent_conversations(aid)
    return [
        {
            "id": c["id"], "session_id": c["session_id"],
            "lead_name": c["lead_name"], "status": c["status"],
            "message_count": c["message_count"],
            "last_message": c["last_message"],
            "created_at": c["created_at"],
            "last_message_at": c["last_message_at"],
        }
        for c in convs
    ]


@app.get("/api/agents/{aid}/conversations/{conv_id}")
async def api_conversation_detail(aid: int, conv_id: int, user_id: int = Depends(_get_uid)):
    conv, msgs = get_conversation_detail(conv_id)
    if not conv or conv["agent_id"] != aid:
        raise HTTPException(404, "Conversation not found")
    return {
        "conversation": dict(conv),
        "messages": [{"role": m["role"], "content": m["content"], "created_at": m["created_at"]} for m in msgs],
    }


@app.post("/api/agents/{agent_id}/chat")
async def api_agent_chat(agent_id: int, request: Request):
    from agent_handler import chat as agent_chat
    body = await request.json()
    session_id = body.get("session_id", "")
    message = (body.get("message") or "").strip()
    if not session_id or not message:
        raise HTTPException(400, "session_id and message required")
    reply = agent_chat(agent_id, session_id, message)
    return {"reply": reply}


@app.get("/api/agents/{agent_id}/greeting")
async def api_agent_greeting(agent_id: int):
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    return {"name": agent["name"], "greeting": agent["greeting"]}


