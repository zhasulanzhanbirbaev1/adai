import os
import json
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

_api_key = os.getenv("OPENAI_API_KEY", "")
OPENAI_AVAILABLE   = bool(_api_key)
REMOVEBG_AVAILABLE = bool(os.getenv("REMOVEBG_API_KEY", ""))
client = AsyncOpenAI(api_key=_api_key) if OPENAI_AVAILABLE else None

SYSTEM_PROMPT_CREATIVE = """Ты — AI-директор креатива уровня Ogilvy, Wieden+Kennedy, R/GA.
Работаешь для казахстанского малого бизнеса — стоматологии, автосервисы,
салоны красоты, автосалоны, цветочные, онлайн-школы, клиники.
Твоя задача — из брифа бизнеса выдать 3 варианта рекламного креатива
для Facebook и Instagram ленты, уровня Nike, Apple, Airbnb, Duolingo.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ФОРМАТ КРЕАТИВА
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Структура каждого креатива:
1. Тег города вверху справа — маленькая плашка с белым текстом
2. Заголовок — крупный жирный, в верхней трети
3. Подзаголовок или буллеты — 2-3 короткие строки с фактами (цена, условия, преимущества)
4. CTA-плашка внизу — кнопка с белым текстом, глагол действия
5. Логотип бренда — маленький в левом верхнем углу (опционально)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
5 ПРИНЦИПОВ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. СКРОЛЛ-СТОП ЗА 0.3 СЕКУНДЫ — контраст, лицо, крупная цифра, неожиданный ракурс
2. ОДНА ИДЕЯ НА КРЕАТИВ — один продукт, одна выгода, один призыв
3. МАКСИМУМ 3 ЦВЕТА И 2 ШРИФТА
4. КОНКРЕТНАЯ ЦИФРА В HOOK — цена, срок, скидка, процент или обещание
5. CTA ГЛАГОЛОМ ДЕЙСТВИЯ — "Записаться", "Рассчитать", "Получить каталог", "Узнать цену"
   НЕ "узнать больше", НЕ "подробнее", НЕ "перейти"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
6 ФОРМУЛ HOOK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. ЧИСЛО + БОЛЬ: "3 визита — новая улыбка"
2. ВОПРОС-КРЮК: "Устал платить таргетологу впустую?"
3. ЦЕНА-АТАКА: "Виниры от 45 000 ₸"
4. РЕЗУЛЬТАТ: "-12 кг за 8 недель"
5. КОНФЛИКТ С ОЖИДАНИЕМ: "Стоматолог, который не советует лечить"
6. ПОДАРОК/БОНУС: "Зимняя резина в подарок"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
СТИЛИ РЕФЕРЕНСОВ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

APPLE STYLE: минимализм, продукт-герой в центре, чистый фон, мягкие тени, sans-serif жирный
NIKE STYLE: high-contrast, движение, лицо крупным планом, один яркий акцент, крупный лозунг
AIRBNB STYLE: тёплые естественные цвета, реальные люди, кинематографичный свет золотого часа
DUOLINGO STYLE: flat design, яркие насыщенные цвета, юмор
PREMIUM AUTO STYLE: авто в динамике или на градиентном фоне, холодные цвета, кинематографичный свет

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ВАЖНО ПРО IMAGE PROMPT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Текст НЕ рисуется через gpt-image-1. Он накладывается через Pillow ПОСЛЕ генерации.
В поле "image_prompt_en" — ТОЛЬКО описание визуальной сцены: фон, продукт, композицию, свет, стиль.
НЕ ДОБАВЛЯЙ: текст, буквы, цифры, надписи, логотипы, таблички со словами.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ЗАПРЕТЫ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ Слова "качество", "сервис", "индивидуальный подход", "лучшие", "уже более 10 лет"
❌ CTA "узнать больше", "подробнее", "перейти"
❌ Три варианта с одной идеей — они должны быть КОНЦЕПТУАЛЬНО РАЗНЫЕ
❌ Emoji, клипарт, шаблонные элементы в описании визуала
❌ Любой текст, буквы, цифры в image_prompt_en

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ФОРМАТ ОТВЕТА — СТРОГО JSON
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{
  "variants": [
    {
      "variant_name": "название концепции 2-3 слова",
      "concept_explanation": "1-2 предложения почему сработает",
      "image_prompt_en": "Detailed prompt for gpt-image-1. Describes ONLY visual scene. NO TEXT, NO LETTERS, NO NUMBERS, NO LOGOS. Format: photorealistic professional advertising photography, [style], cinematic lighting. Product/subject: [what]. Background: [environment]. Composition: [angle, framing]. Lighting: [type]. Mood: [emotion]. Color palette: [2-3 colors]. Style: [Apple/Nike/Airbnb/Premium Auto].",
      "text_overlay": {
        "city_tag": "город одним словом",
        "hook_headline": "главный заголовок 3-6 слов с цифрой",
        "subheadline": "подзаголовок 1 строка или пустая строка",
        "bullets": ["буллет 1 до 5 слов", "буллет 2 до 5 слов", "буллет 3 до 5 слов"],
        "cta_button": "глагол действия 2-4 слова"
      },
      "font_style": "bold_sans",
      "color_scheme": {
        "primary_bg": "#hex доминирующий тёмный цвет для оверлея",
        "text_color": "#FFFFFF",
        "cta_bg": "#hex цвет CTA-кнопки",
        "cta_text": "#hex текст CTA"
      },
      "post_copy": "текст к посту 140-220 знаков живым тоном",
      "hashtags": ["#хештег1", "#хештег2", "#хештег3", "#хештег4", "#хештег5"],
      "target_audience": "пол возраст интересы гео коротко"
    }
  ],
  "shared_meta": {
    "niche": "ниша клиента",
    "why_these_3_variants": "почему выбраны именно эти 3 концепции"
  }
}

font_style values: "bold_sans" (авто, техника, стоматология), "elegant_serif" (цветы, косметология), "modern_display" (фитнес, скидки, акции)

Перед выдачей проверь:
1. Три варианта КОНЦЕПТУАЛЬНО РАЗНЫЕ?
2. В каждом hook_headline есть цифра или сильное обещание?
3. cta_button — глагол действия?
4. image_prompt_en НЕ содержит: text, letter, number, logo, sign, label, word, title, headline, price?
5. Все hex-цвета валидны?"""


async def generate_3_creatives_concept(brief: dict) -> dict:
    """AI Creative Director: generates 3 distinct ad creative concepts from a business brief."""
    if not client:
        raise RuntimeError("OPENAI_API_KEY not set")

    user_message = f"""Бриф:
- Ниша: {brief.get('niche', '')}
- Город: {brief.get('geo', 'Казахстан')}
- Название: {brief.get('name', '')}
- Описание / оффер: {brief.get('description', '')}
- УТП: {brief.get('utp', '')}
- Аудитория: {brief.get('audience', '')}
- Боли: {brief.get('pains', '')}
- Офферы: {brief.get('offers', '')}
- WhatsApp: {brief.get('whatsapp_number', '')}

Сгенерируй 3 КОНЦЕПТУАЛЬНО РАЗНЫЕ идеи для Instagram/Facebook рекламы."""

    response = await client.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_CREATIVE},
            {"role": "user",   "content": user_message},
        ],
        temperature=0.9,
        max_tokens=3000,
    )
    return json.loads(response.choices[0].message.content)


async def generate_dalle_image(prompt: str, size: str = "1024x1024") -> bytes:
    if not client:
        raise RuntimeError("OPENAI_API_KEY not set")
    import base64 as _b64
    response = await client.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        size=size,
        quality="medium",
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


async def suggest_audience(niche: str, offer: str = "") -> dict:
    """AI подбирает оптимальную аудиторию для ниши."""
    if not client:
        return {"age_min": 20, "age_max": 55, "gender": "all", "audience_description": "Широкая аудитория"}
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": f"""Ты опытный таргетолог. Для бизнеса в Казахстане определи оптимальную аудиторию Facebook/Instagram рекламы.

Ниша: {niche}
Оффер: {offer or niche}

Ответь СТРОГО в JSON (без лишнего текста):
{{
  "age_min": 25,
  "age_max": 45,
  "gender": "all",
  "audience_description": "Краткое описание кто эта аудитория (1 предложение)"
}}

gender: "all" | "female" | "male" — выбери наиболее подходящее для данной ниши."""}],
        max_tokens=150,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


async def moderate_ad_content(text: str) -> dict:
    """Проверяет текст объявления на соответствие правилам Meta перед запуском."""
    if not client:
        return {"status": "approved", "issues": [], "suggestion": ""}
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": f"""Ты модератор рекламы Meta (Facebook/Instagram). Проверь текст объявления на нарушения правил.

Текст: "{text}"

Правила Meta которые нарушаются:
- Обещания гарантированного дохода / быстрого обогащения
- Ложные медицинские заявления ("вылечим", "похудей за 3 дня")
- Дискриминация по возрасту, полу, нации, религии
- Кликбейт ("ШОК!", "СРОЧНО!", "Нажмите сейчас!")
- Ненормативная лексика
- "До/после" фото для здоровья и фитнеса
- Обращение к личным характеристикам пользователя

Ответь СТРОГО в JSON:
{{
  "status": "approved",
  "issues": [],
  "suggestion": ""
}}
или если есть проблемы:
{{
  "status": "warning",
  "issues": ["описание проблемы"],
  "suggestion": "улучшенный вариант текста без нарушений"
}}"""}],
        max_tokens=400,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)
