import sqlite3
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
DB_PATH = os.getenv("DB_PATH", "targetolog.db")

PLANS = {
    "month_1": {"name": "1 месяц",  "days": 30,  "price_kzt": 30000},
    "month_2": {"name": "2 месяца", "days": 60,  "price_kzt": 54000},
    "month_3": {"name": "3 месяца", "days": 90,  "price_kzt": 80000},
    "month_6": {"name": "6 месяцев","days": 180, "price_kzt": 140000},
}


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                trial_ends_at TEXT,
                target_cpl REAL DEFAULT 0,
                whatsapp TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                plan TEXT NOT NULL,
                started_at TEXT DEFAULT (datetime('now')),
                expires_at TEXT NOT NULL,
                payment_id TEXT,
                active INTEGER DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS facebook_tokens (
                user_id INTEGER PRIMARY KEY,
                access_token TEXT NOT NULL,
                ad_account_id TEXT NOT NULL,
                token_expires TEXT,
                connected_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                type TEXT DEFAULT 'photo',
                goal TEXT DEFAULT 'whatsapp',
                geo TEXT DEFAULT 'Алматы',
                budget REAL DEFAULT 0,
                target_cpl REAL DEFAULT 0,
                meta_campaign_id TEXT,
                meta_adset_id TEXT,
                active INTEGER DEFAULT 1,
                paused_by_ai INTEGER DEFAULT 0,
                ai_scenario TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS campaign_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                impressions INTEGER DEFAULT 0,
                clicks INTEGER DEFAULT 0,
                leads INTEGER DEFAULT 0,
                spent REAL DEFAULT 0,
                UNIQUE(campaign_id, date),
                FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
            );
            CREATE TABLE IF NOT EXISTS ai_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                scenario TEXT,
                decision TEXT NOT NULL,
                reason TEXT,
                old_value TEXT,
                new_value TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
            );
        """)
        # Migrations for existing DBs
        for col_sql in [
            "ALTER TABLE users ADD COLUMN target_cpl REAL DEFAULT 0",
            "ALTER TABLE users ADD COLUMN whatsapp TEXT",
            "ALTER TABLE campaigns ADD COLUMN ai_scenario TEXT",
        ]:
            try:
                conn.execute(col_sql)
            except Exception:
                pass
    print(f"[DB] Initialized: {DB_PATH}")


# ── Users ──────────────────────────────────────────────────────────────────────

def get_user(user_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def create_user(user_id: int, username: str, first_name: str):
    trial_ends = (datetime.utcnow() + timedelta(days=7)).isoformat()
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, username, first_name, trial_ends_at) VALUES (?, ?, ?, ?)",
            (user_id, username, first_name, trial_ends),
        )
    return get_user(user_id)


def update_user_settings(user_id: int, target_cpl: float = None, whatsapp: str = None):
    fields, vals = [], []
    if target_cpl is not None:
        fields.append("target_cpl = ?"); vals.append(target_cpl)
    if whatsapp is not None:
        fields.append("whatsapp = ?"); vals.append(whatsapp)
    if not fields:
        return
    vals.append(user_id)
    with get_conn() as conn:
        conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", vals)


def is_trial_active(user_id: int) -> bool:
    user = get_user(user_id)
    if not user or not user["trial_ends_at"]:
        return False
    return datetime.fromisoformat(user["trial_ends_at"]) > datetime.utcnow()


def is_subscribed(user_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM subscriptions WHERE user_id=? AND active=1 AND expires_at > datetime('now')",
            (user_id,),
        ).fetchone()
    return row is not None


def has_access(user_id: int) -> bool:
    return is_trial_active(user_id) or is_subscribed(user_id)


def get_active_subscription(user_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM subscriptions WHERE user_id=? AND active=1 AND expires_at > datetime('now') ORDER BY expires_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()


def activate_subscription(user_id: int, plan: str, payment_id: str = None):
    plan_info = PLANS[plan]
    expires = (datetime.utcnow() + timedelta(days=plan_info["days"])).isoformat()
    with get_conn() as conn:
        conn.execute("UPDATE subscriptions SET active=0 WHERE user_id=? AND active=1", (user_id,))
        conn.execute(
            "INSERT INTO subscriptions (user_id, plan, expires_at, payment_id, active) VALUES (?,?,?,?,1)",
            (user_id, plan, expires, payment_id),
        )


# ── Facebook ───────────────────────────────────────────────────────────────────

def save_fb_token(user_id: int, access_token: str, ad_account_id: str, token_expires: str = None):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO facebook_tokens (user_id, access_token, ad_account_id, token_expires, connected_at)
               VALUES (?,?,?,?,datetime('now'))
               ON CONFLICT(user_id) DO UPDATE SET
                 access_token=excluded.access_token, ad_account_id=excluded.ad_account_id,
                 token_expires=excluded.token_expires, connected_at=excluded.connected_at""",
            (user_id, access_token, ad_account_id, token_expires),
        )


def get_fb_token(user_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM facebook_tokens WHERE user_id=?", (user_id,)).fetchone()


def upsert_campaign_from_fb(user_id: int, meta_campaign_id: str, name: str,
                             objective: str, daily_budget: float, status: str):
    active = 1 if status == "ACTIVE" else 0
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM campaigns WHERE meta_campaign_id=? AND user_id=?",
            (meta_campaign_id, user_id),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE campaigns SET name=?, budget=?, active=? WHERE id=?",
                (name, daily_budget, active, existing["id"]),
            )
            return existing["id"]
        cur = conn.execute(
            "INSERT INTO campaigns (user_id, name, type, goal, budget, meta_campaign_id, active) "
            "VALUES (?,?,?,?,?,?,?)",
            (user_id, name, "photo", objective or "whatsapp", daily_budget, meta_campaign_id, active),
        )
        return cur.lastrowid


# ── Campaigns ──────────────────────────────────────────────────────────────────

def get_campaigns(user_id: int, active_only: bool = False):
    q = "SELECT * FROM campaigns WHERE user_id=?"
    if active_only:
        q += " AND active=1"
    q += " ORDER BY created_at DESC"
    with get_conn() as conn:
        return conn.execute(q, (user_id,)).fetchall()


def get_all_active_campaigns():
    with get_conn() as conn:
        return conn.execute(
            "SELECT c.*, ft.access_token, ft.ad_account_id FROM campaigns c "
            "JOIN facebook_tokens ft ON c.user_id = ft.user_id WHERE c.active=1"
        ).fetchall()


def get_all_users_with_campaigns():
    with get_conn() as conn:
        return conn.execute(
            "SELECT DISTINCT user_id FROM campaigns WHERE active=1"
        ).fetchall()


def create_campaign(user_id: int, name: str, camp_type: str, goal: str,
                    geo: str, budget: float, target_cpl: float) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO campaigns (user_id, name, type, goal, geo, budget, target_cpl) VALUES (?,?,?,?,?,?,?)",
            (user_id, name, camp_type, goal, geo, budget, target_cpl),
        )
        return cur.lastrowid


def toggle_campaign(campaign_id: int, user_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT active FROM campaigns WHERE id=? AND user_id=?", (campaign_id, user_id)).fetchone()
        if not row:
            return False
        new_active = 0 if row["active"] else 1
        conn.execute("UPDATE campaigns SET active=?, paused_by_ai=0 WHERE id=?", (new_active, campaign_id))
        return bool(new_active)


def pause_campaign(campaign_id: int, by_ai: bool = False, scenario: str = None):
    with get_conn() as conn:
        conn.execute(
            "UPDATE campaigns SET active=0, paused_by_ai=?, ai_scenario=? WHERE id=?",
            (1 if by_ai else 0, scenario, campaign_id),
        )


def update_campaign_budget(campaign_id: int, new_budget: float):
    with get_conn() as conn:
        conn.execute("UPDATE campaigns SET budget=? WHERE id=?", (new_budget, campaign_id))


# ── Stats ──────────────────────────────────────────────────────────────────────

def upsert_campaign_stats(campaign_id: int, date: str, impressions: int,
                          clicks: int, leads: int, spent: float):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO campaign_stats (campaign_id, date, impressions, clicks, leads, spent)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(campaign_id, date) DO UPDATE SET
                 impressions=excluded.impressions, clicks=excluded.clicks,
                 leads=excluded.leads, spent=excluded.spent""",
            (campaign_id, date, impressions, clicks, leads, spent),
        )


def get_campaign_stats(campaign_id: int, days: int = 7):
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM campaign_stats WHERE campaign_id=? AND date>=? ORDER BY date DESC",
            (campaign_id, cutoff),
        ).fetchall()


def get_user_stats_summary(user_id: int, days: int = 30) -> dict:
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    with get_conn() as conn:
        row = conn.execute(
            """SELECT COALESCE(SUM(cs.impressions),0) AS impressions,
                      COALESCE(SUM(cs.clicks),0) AS clicks,
                      COALESCE(SUM(cs.leads),0) AS leads,
                      COALESCE(SUM(cs.spent),0) AS spent
               FROM campaign_stats cs
               JOIN campaigns c ON cs.campaign_id = c.id
               WHERE c.user_id=? AND cs.date>=?""",
            (user_id, cutoff),
        ).fetchone()
        daily = conn.execute(
            """SELECT cs.date, COALESCE(SUM(cs.spent),0) as spent
               FROM campaign_stats cs
               JOIN campaigns c ON cs.campaign_id = c.id
               WHERE c.user_id=? AND cs.date>=?
               GROUP BY cs.date ORDER BY cs.date""",
            (user_id, cutoff),
        ).fetchall()
    return {
        "impressions": row["impressions"],
        "clicks": row["clicks"],
        "leads": row["leads"],
        "spent": row["spent"],
        "daily": [{"date": r["date"], "spent": r["spent"]} for r in daily],
    }


def get_yesterday_stats(user_id: int) -> dict:
    yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    with get_conn() as conn:
        row = conn.execute(
            """SELECT COALESCE(SUM(cs.impressions),0) AS impressions,
                      COALESCE(SUM(cs.clicks),0) AS clicks,
                      COALESCE(SUM(cs.leads),0) AS leads,
                      COALESCE(SUM(cs.spent),0) AS spent
               FROM campaign_stats cs
               JOIN campaigns c ON cs.campaign_id = c.id
               WHERE c.user_id=? AND cs.date=?""",
            (user_id, yesterday),
        ).fetchone()
    return dict(row) if row else {"impressions": 0, "clicks": 0, "leads": 0, "spent": 0}


# ── AI Decisions ───────────────────────────────────────────────────────────────

def log_ai_decision(campaign_id: int, user_id: int, scenario: str, decision: str,
                    reason: str, old_value: str = None, new_value: str = None):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO ai_decisions (campaign_id,user_id,scenario,decision,reason,old_value,new_value) VALUES (?,?,?,?,?,?,?)",
            (campaign_id, user_id, scenario, decision, reason, old_value, new_value),
        )


def get_ai_log(user_id: int, limit: int = 20):
    with get_conn() as conn:
        return conn.execute(
            """SELECT ad.*, c.name AS campaign_name FROM ai_decisions ad
               JOIN campaigns c ON ad.campaign_id = c.id
               WHERE ad.user_id=? ORDER BY ad.created_at DESC LIMIT ?""",
            (user_id, limit),
        ).fetchall()


def get_today_ai_log(user_id: int):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    with get_conn() as conn:
        return conn.execute(
            """SELECT ad.*, c.name AS campaign_name FROM ai_decisions ad
               JOIN campaigns c ON ad.campaign_id = c.id
               WHERE ad.user_id=? AND ad.created_at LIKE ? ORDER BY ad.created_at DESC""",
            (user_id, f"{today}%"),
        ).fetchall()


# ── Admin ──────────────────────────────────────────────────────────────────────

def get_admin_stats() -> dict:
    with get_conn() as conn:
        total   = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        paying  = conn.execute("SELECT COUNT(DISTINCT user_id) FROM subscriptions WHERE active=1 AND expires_at > datetime('now')").fetchone()[0]
        trial   = conn.execute("SELECT COUNT(*) FROM users WHERE trial_ends_at > datetime('now')").fetchone()[0]
        camps   = conn.execute("SELECT COUNT(*) FROM campaigns WHERE active=1").fetchone()[0]
        revenue = conn.execute(
            "SELECT SUM(CASE plan WHEN 'month_1' THEN 30000 WHEN 'month_2' THEN 54000 WHEN 'month_3' THEN 80000 WHEN 'month_6' THEN 140000 ELSE 0 END) "
            "FROM subscriptions WHERE active=1 AND expires_at > datetime('now')"
        ).fetchone()[0] or 0
    return {"total_users": total, "paying": paying, "trial": trial, "campaigns": camps, "mrr": revenue}


if __name__ == "__main__":
    init_db()
    print("[DB] Schema created successfully.")
