import logging
import os
from datetime import date, datetime, timedelta, timezone
import requests
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import (
    get_all_active_campaigns, get_campaign_stats, get_user_stats_summary,
    get_yesterday_stats, get_all_users_with_campaigns,
    pause_campaign, update_campaign_budget, log_ai_decision,
    upsert_campaign_stats, get_campaigns, get_users_with_fb_tokens,
    mark_budget_alert_sent,
)

logger = logging.getLogger(__name__)

META_API_BASE    = "https://graph.facebook.com/v19.0"
ALMATY_TZ        = timezone(timedelta(hours=5))
MIN_IMPRESSIONS  = 100
CTR_VAMPIRE      = 0.5   # % — ниже → Вампир (пауза)
CTR_SLUMP_MAX    = 2.0   # % — ниже + плохой CPL → Просадка
CTR_SCALE        = 3.0   # % — выше + хороший CPL → масштаб
BUDGET_BOOST     = 1.20  # +20%
BUDGET_PACING_ALERT_PCT = float(os.environ.get("BUDGET_PACING_ALERT_PCT", "90"))


# ── Meta API ───────────────────────────────────────────────────────────────────

def sync_fb_campaigns(user_id: int, access_token: str, ad_account_id: str) -> int:
    """Import campaigns from Facebook into local DB. Returns number synced."""
    from database import upsert_campaign_from_fb
    try:
        resp = requests.get(
            f"{META_API_BASE}/{ad_account_id}/campaigns",
            params={
                "access_token": access_token,
                "fields": "id,name,status,objective,daily_budget",
                "filtering": '[{"field":"effective_status","operator":"IN","value":["ACTIVE","PAUSED"]}]',
                "limit": 100,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        for c in data:
            budget_kzt = int(c.get("daily_budget", 0)) / 100
            upsert_campaign_from_fb(
                user_id=user_id,
                meta_campaign_id=c["id"],
                name=c["name"],
                objective=c.get("objective", ""),
                daily_budget=budget_kzt,
                status=c.get("status", "PAUSED"),
            )
        logger.info("[FB] Synced %d campaigns for user %d", len(data), user_id)
        return len(data)
    except Exception as e:
        logger.error("[FB] Campaign sync failed for user %d: %s", user_id, e)
        return 0


def _pause_meta_campaign(access_token: str, meta_campaign_id: str) -> bool:
    try:
        resp = requests.post(
            f"{META_API_BASE}/{meta_campaign_id}",
            data={"status": "PAUSED", "access_token": access_token},
            timeout=10,
        )
        return resp.ok
    except Exception as e:
        logger.warning("[FB] Pause failed %s: %s", meta_campaign_id, e)
        return False


def _set_meta_budget(access_token: str, meta_campaign_id: str, daily_budget_kzt: float) -> bool:
    try:
        resp = requests.post(
            f"{META_API_BASE}/{meta_campaign_id}",
            data={"daily_budget": int(daily_budget_kzt * 100), "access_token": access_token},
            timeout=10,
        )
        return resp.ok
    except Exception as e:
        logger.warning("[FB] Budget update failed %s: %s", meta_campaign_id, e)
        return False


def _fetch_meta_stats(access_token: str, meta_campaign_id: str, date_preset: str = "yesterday") -> dict | None:
    try:
        resp = requests.get(
            f"{META_API_BASE}/{meta_campaign_id}/insights",
            params={
                "access_token": access_token,
                "fields": "impressions,clicks,actions,spend",
                "date_preset": date_preset,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if not data:
            return None
        row = data[0]
        leads = sum(
            int(a["value"]) for a in row.get("actions", [])
            if a.get("action_type") in ("lead", "offsite_conversion.fb_pixel_lead")
        )
        return {
            "impressions": int(row.get("impressions", 0)),
            "clicks":      int(row.get("clicks", 0)),
            "leads":       leads,
            "spent":       float(row.get("spend", 0)),
        }
    except Exception as e:
        logger.warning("Meta API error for %s: %s", meta_campaign_id, e)
        return None


# ── 4 Сценария ИИ ─────────────────────────────────────────────────────────────

def _classify_scenario(ctr: float, cpl: float, target_cpl: float) -> str:
    """
    1. Вампир     — CTR < 0.5%: жёстко отключаем
    2. Просадка   — CTR слабый + CPL выше цели: готовим замену
    3. Всё работает — метрики в норме: не мешаем
    4. Масштаб    — CTR > 3% + хороший CPL: поднимаем бюджет
    """
    if ctr < CTR_VAMPIRE:
        return "🧛 Вампир"
    if target_cpl > 0 and cpl > target_cpl:
        return "⚠️ Просадка"
    if ctr >= CTR_SCALE and (target_cpl == 0 or cpl <= target_cpl):
        return "🚀 Масштаб"
    return "✅ Работает"


# ── Синхронизация статистики (каждый час) ──────────────────────────────────────

async def sync_stats(bot):
    campaigns = get_all_active_campaigns()
    today = date.today().isoformat()
    synced = 0
    for c in campaigns:
        if not c["meta_campaign_id"] or not c["access_token"]:
            continue
        stats = _fetch_meta_stats(c["access_token"], c["meta_campaign_id"])
        if stats:
            upsert_campaign_stats(c["id"], today, **stats)
            synced += 1
    logger.info("[AI] Stats synced: %d campaigns", synced)


# ── Анализ кампаний (каждые 6 часов) ──────────────────────────────────────────

async def analyze_campaigns(bot):
    campaigns = get_all_active_campaigns()
    logger.info("[AI] Analyzing %d campaigns", len(campaigns))

    for c in campaigns:
        recent = get_campaign_stats(c["id"], days=7)
        if not recent:
            continue

        impressions = sum(r["impressions"] for r in recent)
        clicks      = sum(r["clicks"]      for r in recent)
        leads       = sum(r["leads"]       for r in recent)
        spent       = sum(r["spent"]       for r in recent)

        if impressions < MIN_IMPRESSIONS:
            continue

        ctr        = clicks / impressions * 100
        cpl        = spent / leads if leads > 0 else float("inf")
        target_cpl = c["target_cpl"] or 0

        scenario = _classify_scenario(ctr, cpl, target_cpl)
        decision = reason = old_val = new_val = None

        if scenario == "🧛 Вампир":
            decision = "⏸ Кампания поставлена на паузу"
            reason   = f"CTR {ctr:.2f}% — ниже порога {CTR_VAMPIRE}%. Бюджет сгорает впустую."
            old_val, new_val = "активна", "пауза"
            if c["meta_campaign_id"] and c["access_token"]:
                _pause_meta_campaign(c["access_token"], c["meta_campaign_id"])
            pause_campaign(c["id"], by_ai=True, scenario=scenario)

        elif scenario == "⚠️ Просадка":
            decision = "⏸ Кампания поставлена на паузу"
            reason   = f"CPL {cpl:,.0f} ₸ превышает цель {target_cpl:,.0f} ₸. Нужна новая креатив."
            old_val  = f"CPL {cpl:,.0f} ₸"
            new_val  = "пауза"
            if c["meta_campaign_id"] and c["access_token"]:
                _pause_meta_campaign(c["access_token"], c["meta_campaign_id"])
            pause_campaign(c["id"], by_ai=True, scenario=scenario)

        elif scenario == "🚀 Масштаб":
            new_budget = round(c["budget"] * BUDGET_BOOST, 0)
            decision   = "💰 Бюджет увеличен на 20%"
            reason     = f"CTR {ctr:.2f}%, CPL {cpl:,.0f} ₸ — отличный результат!"
            old_val    = f"{c['budget']:,.0f} ₸/день"
            new_val    = f"{new_budget:,.0f} ₸/день"
            if c["meta_campaign_id"] and c["access_token"]:
                _set_meta_budget(c["access_token"], c["meta_campaign_id"], new_budget)
            update_campaign_budget(c["id"], new_budget)

        else:
            continue  # ✅ Работает — не мешаем

        log_ai_decision(c["id"], c["user_id"], scenario, decision, reason, old_val, new_val)

        try:
            await bot.send_message(
                chat_id=c["user_id"],
                text=(
                    f"{scenario}\n\n"
                    f"📁 *{c['name']}*\n"
                    f"➡️ {decision}\n"
                    f"💬 {reason}"
                    + (f"\n📊 {old_val} → {new_val}" if old_val else "")
                ),
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error("Notify user %s failed: %s", c["user_id"], e)

    logger.info("[AI] Analysis complete.")


# ── Ежедневный отчёт в 9:00 Алматы ────────────────────────────────────────────

async def daily_report(bot):
    users = get_all_users_with_campaigns()
    logger.info("[AI] Sending daily reports to %d users", len(users))

    for row in users:
        user_id = row["user_id"]
        stats = get_yesterday_stats(user_id)

        if stats["impressions"] == 0:
            continue

        camps   = get_campaigns(user_id, active_only=True)
        n_camps = len(camps)
        ctr     = stats["clicks"] / stats["impressions"] * 100 if stats["impressions"] > 0 else 0
        cpl     = stats["spent"] / stats["leads"] if stats["leads"] > 0 else 0

        yesterday_str = (datetime.utcnow() - timedelta(days=1)).strftime("%d.%m.%Y")

        base_url = __import__("os").environ.get("BASE_URL", "https://like-ai-production.up.railway.app").rstrip("/")
        text = (
            f"📊 *Отчёт за {yesterday_str}*\n\n"
            f"👁 Показы: *{stats['impressions']:,}*\n"
            f"🖱 Клики: *{stats['clicks']:,}* (CTR {ctr:.2f}%)\n"
            f"🎯 Заявки: *{stats['leads']}*"
            + (f" (CPL {cpl:,.0f} ₸)" if cpl > 0 else "") + "\n"
            f"💰 Потрачено: *{stats['spent']:,.0f} ₸*\n"
            f"📁 Активных кампаний: {n_camps}\n\n"
            f"[Открыть дашборд]({base_url}/app?user_id={user_id})"
        )

        try:
            await bot.send_message(chat_id=user_id, text=text, parse_mode="Markdown")
        except Exception as e:
            logger.error("Daily report failed for user %s: %s", user_id, e)


# ── Проверка истечения FB токенов (раз в сутки) ───────────────────────────────

async def check_token_expiry(bot):
    rows = get_users_with_fb_tokens()
    now = datetime.utcnow()
    for row in rows:
        user_id = row["user_id"]
        try:
            if row["token_expires"]:
                expiry = datetime.fromisoformat(row["token_expires"])
            elif row["connected_at"]:
                expiry = datetime.fromisoformat(row["connected_at"]) + timedelta(days=60)
            else:
                continue
        except Exception:
            continue

        days_left = (expiry - now).days

        if days_left <= 0:
            msg = (
                "❌ *Токен Facebook истёк*\n\n"
                "ИИ-мониторинг приостановлен — данные не обновляются.\n\n"
                "Переподключи Facebook: /token"
            )
        elif days_left <= 7:
            msg = (
                f"⚠️ *Токен Facebook истекает через {days_left} дн.*\n\n"
                f"После этого ИИ перестанет управлять рекламой.\n\n"
                f"Переподключи заранее: /token"
            )
        else:
            continue

        try:
            await bot.send_message(chat_id=user_id, text=msg, parse_mode="Markdown")
        except Exception as e:
            logger.error("Token expiry notify failed for %s: %s", user_id, e)

    logger.info("[AI] Token expiry check done for %d users", len(rows))


# ── Авто-пауза при перерасходе бюджета (каждые 30 минут) ──────────────────────

async def check_budget_pacing(bot):
    """Если кампания уже потратила BUDGET_PACING_ALERT_PCT% дневного бюджета, а
    календарный день (Алматы) ещё не закончился — ставим на паузу, чтобы не сжечь
    остаток бюджета впустую, и уведомляем. Возобновление — вручную (как и для
    остальных AI-сценариев)."""
    campaigns = get_all_active_campaigns()
    today = datetime.now(ALMATY_TZ).date().isoformat()
    scenario = "🔥 Сгорает бюджет"

    for c in campaigns:
        if not c["meta_campaign_id"] or not c["access_token"] or not c["budget"]:
            continue
        if c.get("budget_alert_sent_date") == today:
            continue

        stats = _fetch_meta_stats(c["access_token"], c["meta_campaign_id"], date_preset="today")
        if not stats:
            continue

        pct = stats["spent"] / c["budget"] * 100
        if pct < BUDGET_PACING_ALERT_PCT:
            continue

        mark_budget_alert_sent(c["id"], today)
        _pause_meta_campaign(c["access_token"], c["meta_campaign_id"])
        pause_campaign(c["id"], by_ai=True, scenario=scenario)
        reason = f"Потрачено {stats['spent']:,.0f} ₸ из {c['budget']:,.0f} ₸ ({pct:.0f}%) — день ещё не закончился."
        log_ai_decision(
            c["id"], c["user_id"], scenario,
            decision="⏸ Кампания поставлена на паузу",
            reason=reason, old_value="активна", new_value="пауза",
        )
        try:
            await bot.send_message(
                chat_id=c["user_id"],
                text=(
                    f"{scenario}\n\n"
                    f"📁 *{c['name']}*\n"
                    f"➡️ ⏸ Кампания поставлена на паузу\n"
                    f"💬 {reason}"
                ),
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error("Budget pacing alert failed for user %s: %s", c["user_id"], e)

    logger.info("[AI] Budget pacing check done.")


# ── Scheduler ─────────────────────────────────────────────────────────────────

def build_scheduler(bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(sync_stats,          "interval", hours=1,  args=[bot], id="sync")
    scheduler.add_job(analyze_campaigns,   "interval", hours=6,  args=[bot], id="analyze",
                      misfire_grace_time=300)
    scheduler.add_job(daily_report,        "cron", hour=9,  minute=0,
                      timezone=ALMATY_TZ, args=[bot], id="daily_report")
    scheduler.add_job(check_token_expiry,  "cron", hour=10, minute=0,
                      timezone=ALMATY_TZ, args=[bot], id="token_expiry")
    scheduler.add_job(check_budget_pacing, "interval", minutes=30, args=[bot], id="budget_pacing",
                      misfire_grace_time=300)
    return scheduler
