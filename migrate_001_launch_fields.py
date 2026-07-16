import os
from dotenv import load_dotenv
import psycopg2
from urllib.parse import urlparse

load_dotenv()

DB_URL = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
if not DB_URL:
    raise SystemExit("DATABASE_URL / DATABASE_PUBLIC_URL не задан в .env")

print(f"Подключение: {urlparse(DB_URL).hostname}")
conn = psycopg2.connect(DB_URL)
conn.autocommit = True
cur = conn.cursor()

migrations = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS fb_page_id TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS fb_ad_account_id TEXT",
    "ALTER TABLE directions ADD COLUMN IF NOT EXISTS age_min INT DEFAULT 25",
    "ALTER TABLE directions ADD COLUMN IF NOT EXISTS age_max INT DEFAULT 55",
]
for sql in migrations:
    print(f"→ {sql}")
    cur.execute(sql)
    print("  OK")

cur.close()
conn.close()
print("\nГотово.")
