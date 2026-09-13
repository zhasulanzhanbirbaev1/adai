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


# Campaign modes
# "leads"    → MESSAGES + CONVERSATIONS + broad Advantage+ audience (18-65, all genders)
#              Facebook picks who's most likely to write → maximum leads at lowest CPL
# "whatsapp" → MESSAGES + CONVERSATIONS + user-specified narrow targeting
CAMPAIGN_MODES = {
    "leads":    {"objective": "MESSAGES", "optimization": "CONVERSATIONS", "label": "Максимум лидов"},
    "whatsapp": {"objective": "MESSAGES", "optimization": "CONVERSATIONS", "label": "WhatsApp"},
}


def create_fb_campaign(access_token: str, ad_account_id: str,
                        name: str, mode: str = "leads") -> str:
    cfg = CAMPAIGN_MODES.get(mode, CAMPAIGN_MODES["leads"])
    resp = requests.post(f"{META_API}/{ad_account_id}/campaigns", data={
        "access_token": access_token,
        "name": name,
        "objective": cfg["objective"],
        "status": "ACTIVE",
        "special_ad_categories": "[]",
    })
    data = resp.json()
    if "id" in data:
        return data["id"]
    raise Exception(f"Campaign creation failed: {data}")


def create_fb_adset(access_token: str, ad_account_id: str, campaign_id: str,
                     name: str, daily_budget_kzt: float, geo: str,
                     age_min: int, age_max: int, gender: str,
                     whatsapp_number: str, mode: str = "leads") -> str:
    cfg = CAMPAIGN_MODES.get(mode, CAMPAIGN_MODES["leads"])

    # Both modes use the niche-based age/gender from the business brief.
    # "leads" adds more placements (Audience Network) for higher volume in the same audience.
    targeting = {
        "geo_locations": {"countries": ["KZ"]},
        "age_min": age_min,
        "age_max": age_max,
    }
    if gender == "male":
        targeting["genders"] = [1]
    elif gender == "female":
        targeting["genders"] = [2]

    if mode == "leads":
        # Max placements → more impressions in the same niche audience → lower CPL
        targeting["publisher_platforms"] = ["facebook", "instagram", "audience_network"]
        targeting["facebook_positions"]  = ["feed", "story", "reels", "right_hand_column", "marketplace"]
        targeting["instagram_positions"] = ["stream", "story", "reels", "explore"]
        targeting["audience_network_positions"] = ["classic"]
    else:
        # WhatsApp mode — FB + IG only, user controls placement
        targeting["publisher_platforms"] = ["facebook", "instagram"]
        targeting["facebook_positions"]  = ["feed", "story", "reels"]
        targeting["instagram_positions"] = ["stream", "story", "reels", "explore"]

    promoted_object = {}
    if whatsapp_number:
        promoted_object = {"whatsapp_phone_number": whatsapp_number}

    params: dict = {
        "access_token": access_token,
        "name": name,
        "campaign_id": campaign_id,
        "daily_budget": int(daily_budget_kzt * 4.5),
        "billing_event": "IMPRESSIONS",
        "optimization_goal": cfg["optimization"],
        "targeting": json.dumps(targeting),
        "destination_type": "WHATSAPP",
        "status": "PAUSED",
    }
    if promoted_object:
        params["promoted_object"] = json.dumps(promoted_object)

    resp = requests.post(f"{META_API}/{ad_account_id}/adsets", data=params)
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


def upload_video_to_fb(access_token: str, ad_account_id: str,
                        video_bytes: bytes, filename: str = "ad.mp4") -> str:
    """Upload video to Facebook Ad Library. Returns video_id."""
    url = f"{META_API}/{ad_account_id}/advideos"
    resp = requests.post(
        url,
        data={"access_token": access_token, "name": filename},
        files={"source": (filename, video_bytes, "video/mp4")},
        timeout=120,
    )
    data = resp.json()
    if "id" in data:
        return data["id"]
    raise Exception(f"Video upload failed: {data}")


def create_fb_video_ad(access_token: str, ad_account_id: str, adset_id: str,
                        name: str, video_id: str, ad_text: str,
                        page_id: str, whatsapp_number: str = None) -> str:
    """Create a video ad creative and ad. Returns ad_id."""
    cta_value = {"app_destination": "WHATSAPP"}
    if whatsapp_number:
        cta_value["whatsapp_number"] = whatsapp_number

    creative_data = {
        "access_token": access_token,
        "name": f"{name} Creative",
        "object_story_spec": json.dumps({
            "page_id": page_id,
            "video_data": {
                "video_id": video_id,
                "message": ad_text,
                "call_to_action": {
                    "type": "WHATSAPP_MESSAGE",
                    "value": cta_value,
                },
            },
        }),
    }
    cr = requests.post(f"{META_API}/{ad_account_id}/adcreatives", data=creative_data)
    cr_data = cr.json()
    if "id" not in cr_data:
        raise Exception(f"Video creative failed: {cr_data}")

    ad = requests.post(f"{META_API}/{ad_account_id}/ads", data={
        "access_token": access_token,
        "name": name,
        "adset_id": adset_id,
        "creative": json.dumps({"creative_id": cr_data["id"]}),
        "status": "PAUSED",
    })
    ad_data = ad.json()
    if "id" in ad_data:
        return ad_data["id"]
    raise Exception(f"Video ad creation failed: {ad_data}")


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
