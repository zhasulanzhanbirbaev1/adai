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

app = FastAPI(title="Adai API", docs_url="/docs", redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


async def _notify(user_id: int, text: str):
    async with httpx.AsyncClient(timeout=8) as client:
        try:
            await client.post(f"{TG_API}/sendMessage",
                              json={"chat_id": user_id, "text": text, "parse_mode": "Markdown"})
        except Exception as e:
            logger.error("TG notify failed: %s", e)


def _get_uid(user_id: int = Query(..., description="Telegram user ID")) -> int:
    if not get_user(user_id):
        raise HTTPException(404, "User not found")
    return user_id


# в”Ђв”Ђ Health / App в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

@app.get("/")
async def landing():
    return FileResponse(os.path.join(os.path.dirname(__file__), "landing.html"))

@app.get("/health")
async def health():
    return {"status": "ok", "service": "Adai"}

@app.api_route("/app", methods=["GET", "HEAD"])
async def serve_app():
    return FileResponse(os.path.join(os.path.dirname(__file__), "app.html"))


# в”Ђв”Ђ Manual Activation в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

def _check_admin(x_admin_key: str = Header(None, alias="X-Admin-Key")):
    if x_admin_key != ADMIN_KEY:
        raise HTTPException(403, "Forbidden")


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
    await _notify(int(uid), f"вњ… *РџРѕРґРїРёСЃРєР° Р°РєС‚РёРІРёСЂРѕРІР°РЅР°*\n\nРџРµСЂРёРѕРґ: *{PLANS[plan]['name']}*")
    return {"status": "ok"}


# в”Ђв”Ђ Dashboard API в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

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


# в”Ђв”Ђ Campaigns API в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

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
    body = await request.json()
    cid = create_campaign(
        user_id,
        name=body.get("name", "РќРѕРІР°СЏ РєР°РјРїР°РЅРёСЏ"),
        camp_type=body.get("type", "photo"),
        goal=body.get("goal", "whatsapp"),
        geo=body.get("geo", "РђР»РјР°С‚С‹"),
        budget=float(body.get("budget", 0)),
        target_cpl=float(body.get("target_cpl", 0)),
    )
    return {"id": cid, "status": "created"}


@app.patch("/api/campaigns/{campaign_id}/toggle")
async def api_toggle(campaign_id: int, user_id: int = Depends(_get_uid)):
    new_state = toggle_campaign(campaign_id, user_id)
    return {"active": new_state}


# в”Ђв”Ђ Analytics API в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

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


# в”Ђв”Ђ AI Log API в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

@app.get("/api/ai-log")
async def api_ai_log(user_id: int = Depends(_get_uid), limit: int = Query(50)):
    log = get_ai_log(user_id, limit=min(limit, 200))
    return [
        {"id": r.get("id", i), "scenario": r["scenario"],
         "decision": r["decision"], "campaign": r["campaign_name"],
         "created_at": r["created_at"]}
        for i, r in enumerate(log)
    ]


# в”Ђв”Ђ Settings API в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

@app.get("/api/settings")
async def api_settings(user_id: int = Depends(_get_uid)):
    user = get_user(user_id)
    fb   = get_fb_token(user_id)
    sub  = get_active_subscription(user_id)
    return {
        "user": {"id": user["id"], "first_name": user["first_name"],
                 "username": user["username"], "target_cpl": user["target_cpl"],
                 "whatsapp": user["whatsapp"]},
        "facebook": {"connected": fb is not None,
                     "ad_account_id": fb["ad_account_id"] if fb else None,
                     "connected_at": fb["connected_at"][:10] if fb else None},
        "subscription": {"active": sub is not None or is_trial_active(user_id),
                         "plan": sub["plan"] if sub else "trial",
                         "expires": sub["expires_at"][:10] if sub else None,
                         "trial_ends": user["trial_ends_at"][:10] if user["trial_ends_at"] else None},
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
    return {"status": "saved"}


# в”Ђв”Ђ Facebook OAuth в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

_FB_SUCCESS_TMPL = """<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>*{{box-sizing:border-box}}body{{font-family:-apple-system,sans-serif;background:#030712;color:#fff;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}}.card{{background:#0f172a;border:1px solid #1e293b;border-radius:16px;padding:40px;text-align:center;max-width:400px}}.icon{{font-size:56px;margin-bottom:16px}}.title{{font-size:22px;font-weight:700;margin-bottom:8px}}.sub{{color:#64748b;font-size:15px;line-height:1.6}}</style>
<script>setTimeout(()=>location.href='{dashboard_url}',2000)</script></head>
<body><div class="card"><div class="icon">вњ…</div><div class="title">Facebook РїРѕРґРєР»СЋС‡С‘РЅ!</div>
<div class="sub">РљР°РјРїР°РЅРёРё СЃРёРЅС…СЂРѕРЅРёР·РёСЂРѕРІР°РЅС‹.<br><br>РћС‚РєСЂС‹РІР°СЋ РґР°С€Р±РѕСЂРґ...</div></div></body></html>"""

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
        "scope": "ads_management,ads_read,business_management",
        "state": str(user_id),
        "response_type": "code",
    })
    return RedirectResponse(f"https://www.facebook.com/v19.0/dialog/oauth?{params}")


@app.get("/fb/callback")
async def fb_callback(code: str = Query(None), state: str = Query(None),
                      error: str = Query(None), error_description: str = Query(None)):
    if error:
        return HTMLResponse(_FB_ERROR.format(title="РћС‚РјРµРЅР°", msg="Р’С‹ РѕС‚РјРµРЅРёР»Рё РїРѕРґРєР»СЋС‡РµРЅРёРµ Facebook."))
    if not code or not state:
        return HTMLResponse(_FB_ERROR.format(title="РћС€РёР±РєР°", msg="РќРµРІРµСЂРЅС‹Р№ Р·Р°РїСЂРѕСЃ."))

    try:
        user_id = int(state)
    except ValueError:
        return HTMLResponse(_FB_ERROR.format(title="РћС€РёР±РєР°", msg="РќРµРІРµСЂРЅС‹Р№ state."))

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get("https://graph.facebook.com/v19.0/oauth/access_token", params={
            "client_id": FB_APP_ID, "client_secret": FB_APP_SECRET,
            "redirect_uri": FB_REDIRECT, "code": code,
        })
        token_data = r.json()

    if "error" in token_data:
        msg = token_data["error"].get("message", "РћС€РёР±РєР° Facebook")
        return HTMLResponse(_FB_ERROR.format(title="РћС€РёР±РєР° Facebook", msg=msg))

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
        return HTMLResponse(_FB_ERROR.format(title="РђРєРєР°СѓРЅС‚С‹ РЅРµ РЅР°Р№РґРµРЅС‹",
                            msg="Р РµРєР»Р°РјРЅС‹Рµ Р°РєРєР°СѓРЅС‚С‹ Facebook РЅРµ РЅР°Р№РґРµРЅС‹."))

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
<style>body{{font-family:-apple-system,sans-serif;background:#030712;color:#fff;padding:32px;max-width:480px;margin:0 auto}}</style></head>
<body><h2>Р’С‹Р±РµСЂРёС‚Рµ СЂРµРєР»Р°РјРЅС‹Р№ Р°РєРєР°СѓРЅС‚</h2>{items}</body></html>""")

    from ai_manager import sync_fb_campaigns
    import asyncio
    count = await asyncio.get_event_loop().run_in_executor(
        None, sync_fb_campaigns, user_id, long_token, ad_account_id
    )
    sync_text = f"рџ“Љ РЎРёРЅС…СЂРѕРЅРёР·РёСЂРѕРІР°РЅРѕ РєР°РјРїР°РЅРёР№: *{count}*" if count > 0 else "рџ“Љ РђРєС‚РёРІРЅС‹С… РєР°РјРїР°РЅРёР№ РЅРµ РЅР°Р№РґРµРЅРѕ"

    await _notify(user_id,
        f"вњ… *Facebook РїРѕРґРєР»СЋС‡С‘РЅ Рё СЃРёРЅС…СЂРѕРЅРёР·РёСЂРѕРІР°РЅ!*\n\n"
        f"РђРєРєР°СѓРЅС‚: `{ad_account_id}`\n"
        f"{sync_text}")
    dashboard_url = f"{_BASE_URL}/app?user_id={user_id}"
    return HTMLResponse(_FB_SUCCESS_TMPL.format(dashboard_url=dashboard_url))


@app.get("/fb/select")
async def fb_select(user_id: int = Query(...), token: str = Query(...), account_id: str = Query(...)):
    save_fb_token(user_id, token, account_id)
    from ai_manager import sync_fb_campaigns
    count = await asyncio.get_event_loop().run_in_executor(
        None, sync_fb_campaigns, user_id, token, account_id
    )
    sync_text = f"рџ“Љ РЎРёРЅС…СЂРѕРЅРёР·РёСЂРѕРІР°РЅРѕ РєР°РјРїР°РЅРёР№: *{count}*" if count > 0 else "рџ“Љ РђРєС‚РёРІРЅС‹С… РєР°РјРїР°РЅРёР№ РЅРµ РЅР°Р№РґРµРЅРѕ"
    await _notify(user_id,
        f"вњ… *Facebook РїРѕРґРєР»СЋС‡С‘РЅ!*\n\nРђРєРєР°СѓРЅС‚: `{account_id}`\n{sync_text}")
    dashboard_url = f"{_BASE_URL}/app?user_id={user_id}"
    return HTMLResponse(_FB_SUCCESS_TMPL.format(dashboard_url=dashboard_url))


# в”Ђв”Ђ Directions API в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

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
    name = body.get("name", "РќРѕРІРѕРµ РЅР°РїСЂР°РІР»РµРЅРёРµ")
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
        raise HTTPException(400, "Р—Р°РіСЂСѓР·РёС‚Рµ С…РѕС‚СЏ Р±С‹ РѕРґРёРЅ РєСЂРµР°С‚РёРІ")
    body = await request.json()
    ad_text = body.get("ad_text") or d["ad_text"] or d["description"] or "РЎРІСЏР¶РёС‚РµСЃСЊ СЃ РЅР°РјРё"
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
        geo=d["geo"] or "РљР°Р·Р°С…СЃС‚Р°РЅ",
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
        f"рџљЂ *РљР°РјРїР°РЅРёСЏ Р·Р°РїСѓС‰РµРЅР°!*\n\n"
        f"РќР°РїСЂР°РІР»РµРЅРёРµ: *{d['name']}*\n"
        f"РљР°РјРїР°РЅРёСЏ: `{camp_id}`\n"
        f"РћР±СЉСЏРІР»РµРЅРёР№: {len(ad_ids)}\n\n"
        f"РЎС‚Р°С‚СѓСЃ: РЅР° РїСЂРѕРІРµСЂРєРµ Facebook")
    return {"campaign_id": camp_id, "adset_id": adset_id, "ads": ad_ids, "strategy": strategy}


# в”Ђв”Ђ Image Generator API в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

@app.post("/api/generate-banner")
async def api_generate_banner(request: Request, user_id: int = Depends(_get_uid)):
    import base64 as b64mod
    from image_generator import generate_dalle_image, generate_ad_copy, OPENAI_AVAILABLE
    from banner_composer import create_banners

    if not OPENAI_AVAILABLE:
        raise HTTPException(503, "OpenAI API key not configured")

    body = await request.json()

    # Legacy path: user uploads their own photo (AI Studio)
    image_base64 = body.get("image_base64")
    offer        = (body.get("offer") or "").strip()
    if image_base64 and offer:
        try:
            copy      = await generate_ad_copy(offer, body.get("audience") or "", image_base64)
            img_bytes = b64mod.b64decode(image_base64)
            headlines = copy.get("headlines", [offer] * 3)
            banners   = create_banners(img_bytes, headlines, copy.get("bullets", []), copy.get("cta", "РЈР·РЅР°С‚СЊ Р±РѕР»СЊС€Рµ"))
            return {"banners": banners, "copy": copy}
        except Exception as e:
            raise HTTPException(500, str(e))

    # DALL-E path: generate image from description
    description = (body.get("description") or "").strip()
    niche        = (body.get("niche") or "").strip()
    audience     = (body.get("audience") or "РјРµСЃС‚РЅС‹Рµ Р¶РёС‚РµР»Рё").strip()
    style        = body.get("style", "cinematic")

    if not description:
        raise HTTPException(400, "description or (offer + image_base64) required")

    style_prompts = {
        "cinematic": (
            f"Professional cinematic advertising photo for Facebook ad. {description}. "
            "Dramatic lighting, deep shadows, rich colors, photorealistic, 8K, commercial photography."
        ),
        "product": (
            f"Clean product photography for social media ad. {description}. "
            "White or neutral background, studio lighting, sharp focus, commercial quality."
        ),
        "minimal": (
            f"Modern minimalist advertising visual for social media. {description}. "
            "Bold solid color background, geometric shapes, high contrast, editorial style."
        ),
    }
    dalle_prompt = style_prompts.get(style, style_prompts["cinematic"])

    try:
        image_bytes = await generate_dalle_image(dalle_prompt, size="1024x1024")
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        logger.error("DALL-E generation error: %s", e)
        raise HTTPException(500, f"DALL-E error: {str(e)}")

    try:
        photo_b64 = b64mod.b64encode(image_bytes).decode()
        copy = await generate_ad_copy(niche or description, audience, photo_b64)
        headlines = copy.get("headlines", [description] * 3)
        bullets   = copy.get("bullets", [])
        cta       = copy.get("cta", "РЈР·РЅР°С‚СЊ Р±РѕР»СЊС€Рµ")
    except Exception as e:
        logger.error("Ad copy generation error: %s", e)
        headlines = [description, description, description]
        bullets, cta = [], "РЈР·РЅР°С‚СЊ Р±РѕР»СЊС€Рµ"

    banners = create_banners(image_bytes, headlines, bullets, cta)
    return {
        "banners": banners,
        "copy": {"headlines": headlines, "bullets": bullets, "cta": cta},
    }


# в”Ђв”Ђ AI Agents API в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

@app.get("/chat/{agent_id}")
async def serve_chat(agent_id: int):
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(404, "РђРіРµРЅС‚ РЅРµ РЅР°Р№РґРµРЅ")
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
    name = body.get("name", "РњРѕР№ РР-Р°РіРµРЅС‚")
    system_prompt = body.get("system_prompt", "РўС‹ РІРµР¶Р»РёРІС‹Р№ РїРѕРјРѕС‰РЅРёРє.")
    greeting = body.get("greeting", "Р—РґСЂР°РІСЃС‚РІСѓР№С‚Рµ! Р§РµРј РјРѕРіСѓ РїРѕРјРѕС‡СЊ?")
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


