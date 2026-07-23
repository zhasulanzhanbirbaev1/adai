import os
import json
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

_api_key = os.getenv("OPENAI_API_KEY", "")
OPENAI_AVAILABLE   = bool(_api_key)
REMOVEBG_AVAILABLE = bool(os.getenv("REMOVEBG_API_KEY", ""))
client = AsyncOpenAI(api_key=_api_key) if OPENAI_AVAILABLE else None


async def generate_dalle_image(prompt: str, size: str = "1024x1024") -> bytes:
    """Generate an image with gpt-image-1 and return raw PNG bytes."""
    if not client:
        raise RuntimeError("OPENAI_API_KEY not set")
    import base64 as _b64
    response = await client.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        size=size,
        quality="high",
        n=1,
    )
    return _b64.b64decode(response.data[0].b64_json)


async def generate_instagram_copy(niche: str, offer: str, audience: str) -> dict:
    prompt = f"""Ты лучший SMM-копирайтер для Instagram рекламы в Казахстане.

Ниша: {niche}
Оффер: {offer or niche}
Аудитория: {audience or 'местные жители Казахстана'}

Создай тексты для Instagram рекламы. Ответь СТРОГО в JSON:
{{
  "caption": "Основной текст поста (3-5 предложений, эмодзи, живой язык, боль → решение → CTA)",
  "caption_short": "Короткий вариант для карусели (1-2 предложения + CTA)",
  "stories_text": "Текст для Stories — очень короткий, 5-8 слов, цепляющий",
  "hashtags": "#хэштег1 #хэштег2 ... (15-20 релевантных хэштегов на русском и английском для КЗ)",
  "cta_button": "Текст кнопки CTA (2-4 слова)"
}}

Правила:
- caption пишется живым языком, как будто пишет человек
- Начни с боли или вопроса клиента
- Используй эмодзи органично
- Хэштеги: микс популярных КЗ + нишевых
- Всё на русском кроме хэштегов"""

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=600,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


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
