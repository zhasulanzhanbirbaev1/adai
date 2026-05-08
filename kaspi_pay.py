import os
import hmac
import hashlib
import time
import uuid
import requests
from dotenv import load_dotenv

load_dotenv()

PLAN_PRICES_KZT = {
    "month_1": 30000,
    "month_2": 54000,
    "month_3": 80000,
    "month_6": 140000,
}

PLAN_NAMES = {
    "month_1": "like.ai — 1 месяц",
    "month_2": "like.ai — 2 месяца",
    "month_3": "like.ai — 3 месяца",
    "month_6": "like.ai — 6 месяцев",
}

KASPI_MERCHANT_ID = os.getenv("KASPI_MERCHANT_ID", "")
KASPI_API_KEY = os.getenv("KASPI_API_KEY", "")
KASPI_WEBHOOK_URL = os.getenv("KASPI_WEBHOOK_URL", "")
KASPI_TEST = os.getenv("KASPI_TEST", "true").lower() == "true"

KASPI_BASE_URL = "https://api.kaspi.kz/pay" if not KASPI_TEST else "https://test-api.kaspi.kz/pay"
DEMO_MODE = not KASPI_MERCHANT_ID


def _sign(payload: str) -> str:
    return hmac.new(KASPI_API_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()


def create_payment(user_id: int, plan: str, amount: int, description: str) -> dict:
    """
    Returns dict with keys: payment_url, payment_id, demo (bool).
    In demo mode returns a fake URL so the bot can work without real Kaspi credentials.
    """
    payment_id = str(uuid.uuid4())

    if DEMO_MODE:
        return {
            "payment_url": f"https://demo.kaspi.kz/pay/{payment_id}",
            "payment_id": payment_id,
            "demo": True,
        }

    payload = {
        "merchantId": KASPI_MERCHANT_ID,
        "orderId": payment_id,
        "amount": amount,
        "currency": "KZT",
        "description": description,
        "callbackUrl": f"{KASPI_WEBHOOK_URL}/kaspi/webhook",
        "returnUrl": f"https://t.me/{os.getenv('BOT_USERNAME', 'YOUR_BOT')}",
        "extra": {"userId": str(user_id), "plan": plan},
    }

    timestamp = str(int(time.time()))
    sign_str = f"{KASPI_MERCHANT_ID}{payment_id}{amount}{timestamp}"
    headers = {
        "Authorization": f"Bearer {KASPI_API_KEY}",
        "X-Merchant-Id": KASPI_MERCHANT_ID,
        "X-Timestamp": timestamp,
        "X-Signature": _sign(sign_str),
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(f"{KASPI_BASE_URL}/payments/create", json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return {
            "payment_url": data.get("paymentUrl") or data.get("payment_url"),
            "payment_id": payment_id,
            "demo": False,
        }
    except Exception as e:
        return {"error": str(e), "payment_id": payment_id, "demo": False}


def verify_webhook_signature(body: bytes, signature: str) -> bool:
    if DEMO_MODE:
        return True
    expected = hmac.new(KASPI_API_KEY.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def parse_webhook_payload(data: dict) -> dict | None:
    """
    Parses incoming Kaspi webhook and returns normalized dict or None if invalid.
    Expected fields: orderId, status, amount, extra.userId, extra.plan
    """
    status = data.get("status") or data.get("orderStatus")
    if status not in ("PAID", "COMPLETED", "SUCCESS"):
        return None

    extra = data.get("extra") or {}
    user_id = extra.get("userId") or data.get("userId")
    plan = extra.get("plan") or data.get("plan")
    payment_id = data.get("orderId") or data.get("paymentId")

    if not user_id or not plan or not payment_id:
        return None

    return {
        "user_id": int(user_id),
        "plan": plan,
        "payment_id": payment_id,
        "amount": data.get("amount", 0),
    }
