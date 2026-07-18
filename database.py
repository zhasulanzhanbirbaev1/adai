import os
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
_DSN = os.getenv("DATABASE_URL", "")

PLANS = {
    "month_1": {"name": "1 месяц",  "days": 30,  "price_kzt": 30000,  "campaign_limit": 3},
    "month_2": {"name": "Квартал",  "days": 90,  "price_kzt": 54000,  "campaign_limit": None},
    "month_3": {"name": "Полгода",  "days": 180, "price_kzt": 80000,  "campaign_limit": None},
    "month_6": {"name": "Год",      "days": 365, "price_kzt": 140000, "campaign_limit": None},
}


class _Conn:
    def __init__(self):
        self._conn = psycopg2.connect(_DSN)
        self._conn.autocommit = False

    def execute(self, query, params=()):
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(query, params)
        return cur

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        if exc_type:
            self._conn.rollback()
        else:
            self._conn.commit()
        self._conn.close()


def get_conn():
    return _Conn()


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                trial_ends_at TEXT,
                target_cpl REAL DEFAULT 0,
                whatsapp TEXT,
                created_at TEXT DEFAULT (NOW()::TEXT)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id),
                plan TEXT NOT NULL,
                started_at TEXT DEFAULT (NOW()::TEXT),
                expires_at TEXT NOT NULL,
                payment_id TEXT,
                active INTEGER DEFAULT 1
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS facebook_tokens (
                user_id BIGINT PRIMARY KEY REFERENCES users(id),
                access_token TEXT NOT NULL,
                ad_account_id TEXT NOT NULL,
                token_expires TEXT,
                connected_at TEXT DEFAULT (NOW()::TEXT)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS campaigns (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id),
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
                created_at TEXT DEFAULT (NOW()::TEXT)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS campaign_stats (
                id SERIAL PRIMARY KEY,
                campaign_id INTEGER NOT NULL REFERENCES campaigns(id),
                date TEXT NOT NULL,
                impressions INTEGER DEFAULT 0,
                clicks INTEGER DEFAULT 0,
                leads INTEGER DEFAULT 0,
                spent REAL DEFAULT 0,
                UNIQUE(campaign_id, date)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_decisions (
                id SERIAL PRIMARY KEY,
                campaign_id INTEGER NOT NULL REFERENCES campaigns(id),
                user_id BIGINT NOT NULL,
                scenario TEXT,
                decision TEXT NOT NULL,
                reason TEXT,
                old_value TEXT,
                new_value TEXT,
                created_at TEXT DEFAULT (NOW()::TEXT)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS directions (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id),
                name TEXT NOT NULL,
                niche TEXT,
                description TEXT,
                utp TEXT,
                audience TEXT,
                pains TEXT,
                offers TEXT,
                geo TEXT DEFAULT 'Казахстан',
                gender TEXT DEFAULT 'all',
                traffic_dest TEXT DEFAULT 'whatsapp',
                whatsapp_number TEXT,
                daily_budget REAL DEFAULT 5000,
                target_cpl REAL DEFAULT 1500,
                welcome_message TEXT,
                pre_message TEXT,
                ad_text TEXT,
                status TEXT DEFAULT 'draft',
                fb_campaign_id TEXT,
                created_at TEXT DEFAULT (NOW()::TEXT)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS direction_creatives (
                id SERIAL PRIMARY KEY,
                direction_id INTEGER NOT NULL REFERENCES directions(id),
                fb_image_hash TEXT,
                fb_video_id TEXT,
                filename TEXT,
                file_type TEXT DEFAULT 'image',
                created_at TEXT DEFAULT (NOW()::TEXT)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id),
                name TEXT NOT NULL,
                system_prompt TEXT NOT NULL,
                greeting TEXT DEFAULT 'Здравствуйте! Чем могу помочь?',
                model TEXT DEFAULT 'claude-sonnet-4-6',
                active BOOLEAN DEFAULT TRUE,
                created_at TEXT DEFAULT (NOW()::TEXT)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_conversations (
                id SERIAL PRIMARY KEY,
                agent_id INTEGER NOT NULL REFERENCES agents(id),
                session_id TEXT NOT NULL,
                lead_name TEXT,
                lead_phone TEXT,
                status TEXT DEFAULT 'active',
                created_at TEXT DEFAULT (NOW()::TEXT),
                last_message_at TEXT DEFAULT (NOW()::TEXT),
                UNIQUE(agent_id, session_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_messages (
                id SERIAL PRIMARY KEY,
                conversation_id INTEGER NOT NULL REFERENCES agent_conversations(id),
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT DEFAULT (NOW()::TEXT)
            )
        """)
        for col_sql in [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS target_cpl REAL DEFAULT 0",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS whatsapp TEXT",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS ai_scenario TEXT",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS fb_page_id TEXT",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS fb_ad_account_id TEXT",
            "ALTER TABLE directions ADD COLUMN IF NOT EXISTS age_min INT DEFAULT 25",
            "ALTER TABLE directions ADD COLUMN IF NOT EXISTS age_max INT DEFAULT 55",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS budget_alert_sent_date TEXT",
        ]:
            conn.execute(col_sql)
    print("[DB] PostgreSQL initialized")


# ── Users ──────────────────────────────────────────────────────────────────────

def get_user(user_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE id = %s", (user_id,)).fetchone()


def create_user(user_id: int, username: str, first_name: str):
    trial_ends = (datetime.utcnow() + timedelta(days=7)).isoformat()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users (id, username, first_name, trial_ends_at) VALUES (%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING",
            (user_id, username, first_name, trial_ends),
        )
    return get_user(user_id)


def update_user_settings(user_id: int, target_cpl: float = None, whatsapp: str = None):
    fields, vals = [], []
    if target_cpl is not None:
        fields.append("target_cpl = %s"); vals.append(target_cpl)
    if whatsapp is not None:
        fields.append("whatsapp = %s"); vals.append(whatsapp)
    if not fields:
        return
    vals.append(user_id)
    with get_conn() as conn:
        conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = %s", vals)


def is_trial_active(user_id: int) -> bool:
    user = get_user(user_id)
    if not user or not user["trial_ends_at"]:
        return False
    return datetime.fromisoformat(user["trial_ends_at"]) > datetime.utcnow()


def is_subscribed(user_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM subscriptions WHERE user_id=%s AND active=1 AND expires_at > NOW()::TEXT ORDER BY expires_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()
    return row is not None


def has_access(user_id: int) -> bool:
    return is_trial_active(user_id) or is_subscribed(user_id)


def get_active_subscription(user_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM subscriptions WHERE user_id=%s AND active=1 AND expires_at > NOW()::TEXT ORDER BY expires_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()


def activate_subscription(user_id: int, plan: str, payment_id: str = None):
    plan_info = PLANS[plan]
    expires = (datetime.utcnow() + timedelta(days=plan_info["days"])).isoformat()
    with get_conn() as conn:
        conn.execute("UPDATE subscriptions SET active=0 WHERE user_id=%s AND active=1", (user_id,))
        conn.execute(
            "INSERT INTO subscriptions (user_id, plan, expires_at, payment_id, active) VALUES (%s,%s,%s,%s,1)",
            (user_id, plan, expires, payment_id),
        )


# ── Facebook ───────────────────────────────────────────────────────────────────

def save_fb_token(user_id: int, access_token: str, ad_account_id: str, token_expires: str = None):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO facebook_tokens (user_id, access_token, ad_account_id, token_expires, connected_at)
               VALUES (%s,%s,%s,%s,NOW()::TEXT)
               ON CONFLICT(user_id) DO UPDATE SET
                 access_token=EXCLUDED.access_token, ad_account_id=EXCLUDED.ad_account_id,
                 token_expires=EXCLUDED.token_expires, connected_at=EXCLUDED.connected_at""",
            (user_id, access_token, ad_account_id, token_expires),
        )


def get_fb_token(user_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM facebook_tokens WHERE user_id=%s", (user_id,)).fetchone()


def upsert_campaign_from_fb(user_id: int, meta_campaign_id: str, name: str,
                             objective: str, daily_budget: float, status: str):
    active = 1 if status == "ACTIVE" else 0
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM campaigns WHERE meta_campaign_id=%s AND user_id=%s",
            (meta_campaign_id, user_id),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE campaigns SET name=%s, budget=%s, active=%s WHERE id=%s",
                (name, daily_budget, active, existing["id"]),
            )
            return existing["id"]
        cur = conn.execute(
            "INSERT INTO campaigns (user_id, name, type, goal, budget, meta_campaign_id, active) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (user_id, name, "photo", objective or "whatsapp", daily_budget, meta_campaign_id, active),
        )
        return cur.fetchone()["id"]


# ── Campaigns ──────────────────────────────────────────────────────────────────

def get_campaigns(user_id: int, active_only: bool = False):
    q = "SELECT * FROM campaigns WHERE user_id=%s"
    params = [user_id]
    if active_only:
        q += " AND active=1"
    q += " ORDER BY created_at DESC"
    with get_conn() as conn:
        return conn.execute(q, params).fetchall()


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
            "INSERT INTO campaigns (user_id, name, type, goal, geo, budget, target_cpl) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (user_id, name, camp_type, goal, geo, budget, target_cpl),
        )
        return cur.fetchone()["id"]


def toggle_campaign(campaign_id: int, user_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT active FROM campaigns WHERE id=%s AND user_id=%s", (campaign_id, user_id)).fetchone()
        if not row:
            return False
        new_active = 0 if row["active"] else 1
        conn.execute("UPDATE campaigns SET active=%s, paused_by_ai=0 WHERE id=%s", (new_active, campaign_id))
        return bool(new_active)


def pause_campaign(campaign_id: int, by_ai: bool = False, scenario: str = None):
    with get_conn() as conn:
        conn.execute(
            "UPDATE campaigns SET active=0, paused_by_ai=%s, ai_scenario=%s WHERE id=%s",
            (1 if by_ai else 0, scenario, campaign_id),
        )


def update_campaign_budget(campaign_id: int, new_budget: float):
    with get_conn() as conn:
        conn.execute("UPDATE campaigns SET budget=%s WHERE id=%s", (new_budget, campaign_id))


def mark_budget_alert_sent(campaign_id: int, date_str: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE campaigns SET budget_alert_sent_date=%s WHERE id=%s",
            (date_str, campaign_id),
        )


# ── Stats ──────────────────────────────────────────────────────────────────────

def upsert_campaign_stats(campaign_id: int, date: str, impressions: int,
                          clicks: int, leads: int, spent: float):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO campaign_stats (campaign_id, date, impressions, clicks, leads, spent)
               VALUES (%s,%s,%s,%s,%s,%s)
               ON CONFLICT(campaign_id, date) DO UPDATE SET
                 impressions=EXCLUDED.impressions, clicks=EXCLUDED.clicks,
                 leads=EXCLUDED.leads, spent=EXCLUDED.spent""",
            (campaign_id, date, impressions, clicks, leads, spent),
        )


def get_campaign_stats(campaign_id: int, days: int = 7):
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM campaign_stats WHERE campaign_id=%s AND date>=%s ORDER BY date DESC",
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
               WHERE c.user_id=%s AND cs.date>=%s""",
            (user_id, cutoff),
        ).fetchone()
        daily = conn.execute(
            """SELECT cs.date, COALESCE(SUM(cs.spent),0) as spent
               FROM campaign_stats cs
               JOIN campaigns c ON cs.campaign_id = c.id
               WHERE c.user_id=%s AND cs.date>=%s
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
               WHERE c.user_id=%s AND cs.date=%s""",
            (user_id, yesterday),
        ).fetchone()
    return dict(row) if row else {"impressions": 0, "clicks": 0, "leads": 0, "spent": 0}


# ── AI Decisions ───────────────────────────────────────────────────────────────

def log_ai_decision(campaign_id: int, user_id: int, scenario: str, decision: str,
                    reason: str, old_value: str = None, new_value: str = None):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO ai_decisions (campaign_id,user_id,scenario,decision,reason,old_value,new_value) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (campaign_id, user_id, scenario, decision, reason, old_value, new_value),
        )


def get_ai_log(user_id: int, limit: int = 20):
    with get_conn() as conn:
        return conn.execute(
            """SELECT ad.*, c.name AS campaign_name FROM ai_decisions ad
               JOIN campaigns c ON ad.campaign_id = c.id
               WHERE ad.user_id=%s ORDER BY ad.created_at DESC LIMIT %s""",
            (user_id, limit),
        ).fetchall()


def get_today_ai_log(user_id: int):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    with get_conn() as conn:
        return conn.execute(
            """SELECT ad.*, c.name AS campaign_name FROM ai_decisions ad
               JOIN campaigns c ON ad.campaign_id = c.id
               WHERE ad.user_id=%s AND ad.created_at LIKE %s ORDER BY ad.created_at DESC""",
            (user_id, f"{today}%"),
        ).fetchall()


# ── Admin ──────────────────────────────────────────────────────────────────────

def get_admin_stats() -> dict:
    with get_conn() as conn:
        total   = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
        paying  = conn.execute("SELECT COUNT(DISTINCT user_id) as c FROM subscriptions WHERE active=1 AND expires_at > NOW()::TEXT").fetchone()["c"]
        trial   = conn.execute("SELECT COUNT(*) as c FROM users WHERE trial_ends_at > NOW()::TEXT").fetchone()["c"]
        camps   = conn.execute("SELECT COUNT(*) as c FROM campaigns WHERE active=1").fetchone()["c"]
        revenue = conn.execute(
            "SELECT COALESCE(SUM(CASE plan WHEN 'month_1' THEN 30000 WHEN 'month_2' THEN 54000 WHEN 'month_3' THEN 80000 WHEN 'month_6' THEN 140000 ELSE 0 END),0) as r "
            "FROM subscriptions WHERE active=1 AND expires_at > NOW()::TEXT"
        ).fetchone()["r"]
    return {"total_users": total, "paying": paying, "trial": trial, "campaigns": camps, "mrr": revenue}


# ── Directions ─────────────────────────────────────────────────────────────────

def create_direction(user_id: int, name: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO directions (user_id, name) VALUES (%s, %s) RETURNING id",
            (user_id, name),
        )
        return cur.fetchone()["id"]


def get_directions(user_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM directions WHERE user_id=%s ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()


def get_direction(direction_id: int, user_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM directions WHERE id=%s AND user_id=%s",
            (direction_id, user_id),
        ).fetchone()


def update_direction(direction_id: int, **kwargs):
    fields = [f"{k}=%s" for k in kwargs]
    vals = list(kwargs.values()) + [direction_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE directions SET {', '.join(fields)} WHERE id=%s", vals)


def add_direction_creative(direction_id: int, filename: str,
                            fb_image_hash: str = None, fb_video_id: str = None,
                            file_type: str = "image") -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO direction_creatives (direction_id, filename, fb_image_hash, fb_video_id, file_type) "
            "VALUES (%s,%s,%s,%s,%s) RETURNING id",
            (direction_id, filename, fb_image_hash, fb_video_id, file_type),
        )
        return cur.fetchone()["id"]


def get_direction_creatives(direction_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM direction_creatives WHERE direction_id=%s ORDER BY created_at DESC",
            (direction_id,),
        ).fetchall()


def get_users_with_fb_tokens():
    with get_conn() as conn:
        return conn.execute(
            "SELECT user_id, connected_at, token_expires FROM facebook_tokens"
        ).fetchall()


def save_user_page_id(user_id: int, page_id: str):
    with get_conn() as conn:
        conn.execute("UPDATE users SET fb_page_id = %s WHERE id = %s", (page_id, user_id))


def save_user_ad_account_id(user_id: int, ad_account_id: str):
    with get_conn() as conn:
        conn.execute("UPDATE users SET fb_ad_account_id = %s WHERE id = %s", (ad_account_id, user_id))


def update_direction_ad_text(direction_id: int, ad_text: str):
    with get_conn() as conn:
        conn.execute("UPDATE directions SET ad_text = %s WHERE id = %s", (ad_text, direction_id))


def update_direction_campaign(direction_id: int, campaign_id: str, status: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE directions SET fb_campaign_id = %s, status = %s WHERE id = %s",
            (campaign_id, status, direction_id),
        )


# ── Agents ─────────────────────────────────────────────────────────────────────

def create_agent(user_id: int, name: str, system_prompt: str, greeting: str = None) -> int:
    g = greeting or "Здравствуйте! Чем могу помочь?"
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO agents (user_id, name, system_prompt, greeting) VALUES (%s,%s,%s,%s) RETURNING id",
            (user_id, name, system_prompt, g),
        )
        return cur.fetchone()["id"]


def get_agent(agent_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM agents WHERE id=%s AND active=TRUE", (agent_id,)).fetchone()


def get_agents(user_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM agents WHERE user_id=%s ORDER BY created_at DESC", (user_id,)
        ).fetchall()


def update_agent(agent_id: int, **kwargs):
    fields = [f"{k}=%s" for k in kwargs]
    vals = list(kwargs.values()) + [agent_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE agents SET {', '.join(fields)} WHERE id=%s", vals)


def get_or_create_conversation(agent_id: int, session_id: str) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM agent_conversations WHERE agent_id=%s AND session_id=%s",
            (agent_id, session_id),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE agent_conversations SET last_message_at=NOW()::TEXT WHERE id=%s",
                (row["id"],),
            )
            return row["id"]
        cur = conn.execute(
            "INSERT INTO agent_conversations (agent_id, session_id) VALUES (%s,%s) RETURNING id",
            (agent_id, session_id),
        )
        return cur.fetchone()["id"]


def save_agent_message(conversation_id: int, role: str, content: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO agent_messages (conversation_id, role, content) VALUES (%s,%s,%s)",
            (conversation_id, role, content),
        )


def get_conversation_messages(conversation_id: int, limit: int = 20):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT role, content FROM agent_messages WHERE conversation_id=%s ORDER BY created_at DESC LIMIT %s",
            (conversation_id, limit),
        ).fetchall()
    return list(reversed(rows))


def get_agent_conversations(agent_id: int, limit: int = 50):
    with get_conn() as conn:
        return conn.execute(
            """SELECT ac.*,
               (SELECT content FROM agent_messages WHERE conversation_id=ac.id ORDER BY created_at DESC LIMIT 1) AS last_message,
               (SELECT COUNT(*) FROM agent_messages WHERE conversation_id=ac.id) AS message_count
               FROM agent_conversations ac
               WHERE ac.agent_id=%s
               ORDER BY ac.last_message_at DESC LIMIT %s""",
            (agent_id, limit),
        ).fetchall()


def get_conversation_detail(conversation_id: int):
    with get_conn() as conn:
        conv = conn.execute("SELECT * FROM agent_conversations WHERE id=%s", (conversation_id,)).fetchone()
        msgs = conn.execute(
            "SELECT role, content, created_at FROM agent_messages WHERE conversation_id=%s ORDER BY created_at ASC",
            (conversation_id,),
        ).fetchall()
    return conv, msgs


if __name__ == "__main__":
    init_db()
    print("[DB] Schema created successfully.")
