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

image_prompt_en ДОЛЖЕН БЫТЬ 120-180 слов. Он описывает одну конкретную сцену со всеми деталями.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ПРИМЕРЫ image_prompt_en ПО НИШАМ (твой уровень — такой же)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

СТОМАТОЛОГИЯ (Apple style):
"Ultra-high-end advertising photography for a luxury dental clinic. Extreme close-up of a perfect set of white teeth — slightly parted lips, no face visible. Soft key light from the upper left creates a delicate specular highlight on the enamel surface. Background: pure white seamless, slightly warm. The lips are naturally tinted, healthy skin texture, no makeup artifacts. Shallow depth of field on a medium-format lens, 1:1 aspect ratio. The image reads as clean, medical, and aspirational simultaneously. Color palette: ivory white, warm nude, soft platinum. Shot on Phase One IQ4, 120mm macro. Photorealistic, no illustration, no CGI feel. The single subject is the teeth — nothing else competes for attention. Mood: confidence, precision, premium care."

АВТОСЕРВИС (Premium Auto style):
"Cinematic advertising shot of a sleek black SUV parked diagonally on polished dark-grey concrete inside a high-tech service bay. Dramatic three-point studio lighting: one cold blue backlight, one warm amber fill from the left, one edge kicker catching the chrome details. The car is immaculate — no mud, perfect reflections across the hood. Background: blurred industrial space with soft bokeh orbs of workshop lights. Camera angle: low-angle wide shot, 24mm, car occupies 70% of the frame. The scene communicates performance and engineering precision. Mood: dark, technical, aspirational. Color palette: midnight black, steel grey, ice blue accent. Photorealistic, shot on Canon EOS R5, hyperdetailed."

САЛОН КРАСОТЫ (Airbnb/editorial style):
"Editorial beauty photography. A woman's hands with perfectly manicured nails — deep burgundy polish — resting on a white marble table. Around them: a single white peony, a small crystal perfume bottle, and a soft silk ribbon out of focus. Natural window light from the right side creates long soft shadows across the marble surface. Background: warm cream linen curtain, blurred. The composition is asymmetric, generous negative space on the left for text. Color palette: burgundy, ivory, champagne gold, pale rose. Shot on Sony A7R V, 85mm f/1.4. Mood: feminine luxury, calm, confidence. No faces, no text, no logos. The hands are the hero — sharp focus on the nails, gentle bokeh beyond."

ЦВЕТОЧНЫЙ БИЗНЕС (editorial warm style):
"Overhead flat-lay advertising photography, shot from directly above. A generous, voluminous bouquet of white and blush garden roses, eucalyptus sprigs, and dried pampas grass arranged loosely on a warm linen surface. Beside it: a kraft paper wrapping half-unfolded, a spool of twine, and one fallen petal. Natural diffused window light — overcast sky — no harsh shadows. The composition has the bouquet off-center to the right, leaving clean linen space on the left. Color palette: blush pink, ivory, sage green, warm wheat. Shot on Hasselblad X2D, 80mm. Mood: romantic, artisan, generous. Ultra-realistic texture on every petal. Photorealistic, no illustration, no AI plastic feel."

ОБЩЕПИТ (editorial warm style):
"Hero food photography for restaurant advertising. A hand-made ceramic bowl of rich, steaming beef pho soup — perfectly arranged sliced meat, fresh herbs, a halved lime, and thin rice noodles visible through the golden broth. A thin wisp of steam rises. Chopsticks rest across the bowl rim. Background: dark reclaimed oak table, a small pinch of chili and cilantro beside the bowl. Side backlight from the upper right creates the steam glow and reflects in the broth surface. Shot at table level, 45-degree angle, 100mm macro lens. Color palette: deep amber, terracotta, emerald herb green. Mood: warmth, abundance, authenticity. Photorealistic, Michelin-guide photo quality."

ФИТНЕС (Nike/dynamic style):
"High-energy sports photography for gym advertising. Dynamic freeze-frame of a muscular athlete's torso mid-movement — a clean deadlift at the top position. Heavy iron barbell, chalk dust suspended in the air around the hands, veins visible on the forearms. Athlete wears a simple black compression shirt. Dramatic high-contrast studio lighting: one hard key light from directly above creates deep dramatic shadows; a cold blue rim light from behind separates the figure from the background. Background: pure black. Camera angle: low-angle, shot from just below hip height. Shot on Nikon Z9, 70-200mm at 135mm. Color palette: carbon black, pure white highlight, electric blue accent. Mood: raw power, discipline, transformation."

КЛИНИКА / МЕДИЦИНА (Apple clinical style):
"Architectural interior photography for a private medical clinic. Empty consultation room — white-on-white aesthetic. Matte white walls, polished light oak floor panels. A single modern examination chair in pearl white, positioned slightly off-center. Large floor-to-ceiling window on the left, sheer curtains diffusing bright natural light across the entire scene. On the wall: a single abstract canvas in pale sand. No medical equipment visible except a slim digital screen on a minimalist arm. The scene is calm, uncluttered, premium. Shot with a tilt-shift lens to keep all horizontal lines perfectly level. Color palette: pure white, warm ivory, light oak, pale sage. Mood: precision, trust, serenity. Photorealistic, no CGI."

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
      "image_prompt_en": "120-180 word scene description matching the niche examples above. Describes ONLY the visual scene — background, subject, composition, light, mood, camera details. NO text, NO letters, NO numbers, NO logos, NO signs. Include: shot type (close-up/wide/overhead), lens/camera reference, exact lighting setup (key+fill+back), color palette (3 specific colors), and mood word. Match the depth and specificity of the niche examples. End with: Photorealistic advertising photography, [Brand Style] aesthetic.",
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
      "aspect_ratio": "4:5",
      "lead_temperature": "hot",
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

aspect_ratio: "4:5" для ленты, "9:16" для Stories, "1:1" для квадрата
lead_temperature: "hot" (прямой оффер с ценой), "warm" (выгода + доверие), "cold" (стоп-скролл, нестандартный ракурс)
font_style values: "bold_sans" (авто, техника, стоматология), "elegant_serif" (цветы, косметология), "modern_display" (фитнес, скидки, акции)

Перед выдачей проверь:
1. Три варианта КОНЦЕПТУАЛЬНО РАЗНЫЕ (тема, стиль, температура лида)?
2. В каждом hook_headline есть цифра или сильное обещание?
3. cta_button — глагол действия?
4. image_prompt_en 120-180 слов, содержит: тип кадра, объект съёмки, фон, свет, камеру, палитру, настроение?
5. image_prompt_en НЕ содержит: text, letter, number, logo, sign, label, word, title, headline, price?
6. Все hex-цвета валидны?"""


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
    import logging as _log
    _logger = _log.getLogger(__name__)

    # Try gpt-image-1 (requires special OpenAI org access)
    try:
        response = await client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size=size,
            quality="medium",
            n=1,
        )
        return _b64.b64decode(response.data[0].b64_json)
    except Exception as _e:
        _logger.warning("gpt-image-1 failed (%s), falling back to dall-e-3", _e)

    # Fallback: dall-e-3 (portrait 1024x1792, square 1024x1024)
    try:
        parts = size.split("x")
        dalle_size = "1024x1792" if len(parts) == 2 and int(parts[0]) < int(parts[1]) else "1024x1024"
    except Exception:
        dalle_size = "1024x1024"
    response = await client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size=dalle_size,
        quality="standard",
        response_format="b64_json",
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


async def generate_banners_from_photo(
    payload: dict,
    image_base64: str,
    niche: str = "",
    restage_mode: str = "local",
    out_dir: str = "/tmp/_ad_out",
) -> dict:
    """
    Photo pipeline: given a client product photo (base64) + creative payload,
    produces rendered ad banners using the cv2/treatments pipeline.

    restage_mode: "off" | "local" | "generative"
    Returns the treatments.render_from_photo() result dict.
    """
    import base64 as _b64
    import tempfile
    import os as _os
    import asyncio

    from openai import OpenAI as _SyncOpenAI

    # Decode photo to a temp file
    img_bytes = _b64.b64decode(image_base64)
    suffix = ".jpg"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        f.write(img_bytes)
        tmp_path = f.name

    try:
        import treatments

        sync_client = None
        if restage_mode == "generative" and _api_key:
            sync_client = _SyncOpenAI(api_key=_api_key)

        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: treatments.render_from_photo(
                payload=payload,
                photo_path=tmp_path,
                out_dir=out_dir,
                strict=False,
                restage_mode=restage_mode,
                niche=niche,
                openai_client=sync_client,
            )
        )
        return result
    finally:
        try:
            _os.unlink(tmp_path)
        except Exception:
            pass


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
