import os
import json
import requests
import logging
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)
META_API = "https://graph.facebook.com/v19.0"
_openai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))


async def generate_brief_strategy(direction: dict) -> dict:
    prompt = f"""Ты AI-таргетолог. Проанализируй бриф бизнеса и создай стратегию запуска рекламной кампании в Facebook/Instagram.

БРИФ:
- Ниша: {direction.get('niche', '')}
- Описание: {direction.get('description', '')}
- УТП: {direction.get('utp', '')}
- Аудитория: {direction.get('audience', '')}
- Боли клиентов: {direction.get('pains', '')}
- Офферы: {direction.get('offers', '')}
- Гео: {direction.get('geo', 'Казахстан')}
- Трафик на: {direction.get('traffic_dest', 'whatsapp')}
- Дневной бюджет: {direction.get('daily_budget', 5000)} ₸
- Целевой CPL: {direction.get('target_cpl', 1500)} ₸

Верни JSON:
{{
  "strategy_text": "Краткое описание стратегии (3-4 предложения)",
  "audience_desc": "Описание целевой аудитории для Facebook",
  "age_min": 20,
  "age_max": 45,
  "budget_recommendation": 5000,
  "expected_cpl": 1500,
  "campaign_name": "Название кампании",
  "ad_texts": {{
    "emotional": "Эмоциональный текст объявления",
    "rational": "Рациональный текст объявления",
    "urgent": "Срочный текст объявления"
  }},
  "day1_plan": "Что делать в первый день",
  "day2_plan": "Что делать на второй день",
  "risks": "Основные риски и как с ними работать"
}}"""

    resp = await _openai.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        max_tokens=1500,
    )
    return json.loads(resp.choices[0].message.content)


def upload_image_to_fb(access_token: str, ad_account_id: str, image_bytes: bytes, filename: str) -> str:
    url = f"{META_API}/{ad_account_id}/adimages"
    resp = requests.post(url, data={"access_token": access_token},
                         files={"filename": (filename, image_bytes, "image/jpeg")})
    data = resp.json()
    if "images" in data:
        return list(data["images"].values())[0]["hash"]
    raise Exception(f"Image upload failed: {data}")


def create_fb_campaign(access_token: str, ad_account_id: str,
                        name: str, objective: str = "MESSAGES") -> str:
    resp = requests.post(f"{META_API}/{ad_account_id}/campaigns", data={
        "access_token": access_token,
        "name": name,
        "objective": objective,
        "status": "PAUSED",
        "special_ad_categories": "[]",
    })
    data = resp.json()
    if "id" in data:
        return data["id"]
    raise Exception(f"Campaign creation failed: {data}")


def create_fb_adset(access_token: str, ad_account_id: str, campaign_id: str,
                     name: str, daily_budget_kzt: float, geo: str,
                     age_min: int, age_max: int, gender: str,
                     whatsapp_number: str) -> str:
    country = "KZ"  # все города и регионы КЗ → страна KZ в Facebook

    targeting = {
        "geo_locations": {"countries": [country]},
        "age_min": age_min,
        "age_max": age_max,
    }
    if gender == "male":
        targeting["genders"] = [1]
    elif gender == "female":
        targeting["genders"] = [2]

    promoted_object = {}
    if whatsapp_number:
        promoted_object = {"whatsapp_phone_number": whatsapp_number}

    resp = requests.post(f"{META_API}/{ad_account_id}/adsets", data={
        "access_token": access_token,
        "name": name,
        "campaign_id": campaign_id,
        "daily_budget": int(daily_budget_kzt * 4.5),
        "billing_event": "IMPRESSIONS",
        "optimization_goal": "CONVERSATIONS",
        "targeting": json.dumps(targeting),
        "promoted_object": json.dumps(promoted_object) if promoted_object else "{}",
        "status": "PAUSED",
    })
    data = resp.json()
    if "id" in data:
        return data["id"]
    raise Exception(f"AdSet creation failed: {data}")


def create_fb_ad(access_token: str, ad_account_id: str, adset_id: str,
                  name: str, image_hash: str, ad_text: str,
                  page_id: str, whatsapp_number: str = None) -> str:
    creative_data = {
        "access_token": access_token,
        "name": f"{name} Creative",
        "object_story_spec": json.dumps({
            "page_id": page_id,
            "link_data": {
                "image_hash": image_hash,
                "message": ad_text,
                "call_to_action": {
                    "type": "WHATSAPP_MESSAGE",
                    "value": {"app_destination": "WHATSAPP"}
                }
            }
        }),
    }
    cr = requests.post(f"{META_API}/{ad_account_id}/adcreatives", data=creative_data)
    cr_data = cr.json()
    if "id" not in cr_data:
        raise Exception(f"Creative failed: {cr_data}")

    ad = requests.post(f"{META_API}/{ad_account_id}/ads", data={
        "access_token": access_token,
        "name": name,
        "adset_id": adset_id,
        "creative": json.dumps({"creative_id": cr_data["id"]}),
        "status": "PAUSED",
        "access_token": access_token,
    })
    ad_data = ad.json()
    if "id" in ad_data:
        return ad_data["id"]
    raise Exception(f"Ad creation failed: {ad_data}")


def get_fb_pages(access_token: str) -> list:
    resp = requests.get(f"{META_API}/me/accounts",
                        params={"access_token": access_token, "fields": "id,name"})
    return resp.json().get("data", [])


def set_campaign_status(access_token: str, campaign_id: str, status: str) -> dict:
    """status = 'ACTIVE' or 'PAUSED'."""
    resp = requests.post(
        f"{META_API}/{campaign_id}",
        data={"status": status, "access_token": access_token},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()
