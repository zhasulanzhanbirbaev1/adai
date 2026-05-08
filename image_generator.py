import os
import json
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

_api_key = os.getenv("OPENAI_API_KEY", "")
OPENAI_AVAILABLE   = bool(_api_key)
REMOVEBG_AVAILABLE = bool(os.getenv("REMOVEBG_API_KEY", ""))
client = AsyncOpenAI(api_key=_api_key) if OPENAI_AVAILABLE else None


async def generate_ad_copy(offer: str, audience: str, image_base64: str = None) -> dict:
    content = []
    if image_base64:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
        })
    content.append({
        "type": "text",
        "text": f"""Ты лучший копирайтер для Facebook/Instagram рекламы в Казахстане.

Оффер: {offer}
Аудитория: {audience or 'местные жители'}

Ответь СТРОГО в JSON:
{{
  "headlines": [
    "Заголовок 1 — главная выгода (3-5 слов)",
    "Заголовок 2 — боль клиента (3-5 слов)",
    "Заголовок 3 — акция/срочность (3-5 слов)"
  ],
  "bullets": ["конкретная выгода с цифрой/фактом", "бонус или условие", "гарантия или результат"],
  "cta": "Действие 2-4 слова"
}}

Правила:
- Заголовки КОРОТКИЕ и цепляющие — не более 5 слов
- Буллеты конкретные: цифры, сроки, цены
- CTA простой: Запишитесь, Звоните, Узнайте цену
- Всё на русском"""
    })
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": content}],
        max_tokens=400,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)
