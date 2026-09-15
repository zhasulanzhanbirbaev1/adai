import os
import json
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

_api_key = os.getenv("OPENAI_API_KEY", "")
OPENAI_AVAILABLE   = bool(_api_key)
REMOVEBG_AVAILABLE = bool(os.getenv("REMOVEBG_API_KEY", ""))
client = AsyncOpenAI(api_key=_api_key) if OPENAI_AVAILABLE else None

SYSTEM_PROMPT_CREATIVE = """Ты — креативный директор перформанс-агентства.
Работаешь с малым и развитым бизнесом в Казахстане: стоматологии, автосервисы,
салоны красоты, автосалоны, цветочные, онлайн-школы, клиники, общепит.
Задача — из брифа выдать ровно 3 креатива для ленты Facebook/Instagram в строгом JSON.
Модель использования: пользователь получает 3 варианта, выбирает один и запускает его. A/B-теста нет.
Значит, твоя работа — не три гипотезы, а три внятных решения с понятным объяснением, какое кому подойдёт.
Все три — лидогенерация. Трафик идёт в WhatsApp.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
0. ВХОДНОЙ КОНТРАКТ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Обязательное поле брифа: ниша. Всё остальное (город, продукт, цена, срок) — опционально.
ЗАПРЕЩЕНО писать цифры (цены, проценты, сроки) в image_prompt_en — DALL-E рисует их криво и это ломает объявление.
В text_overlay (hook_headline, subheadline, bullets, cta_button) цифры ОБЯЗАТЕЛЬНЫ — их рендерит Pillow, они читаются идеально.
Оффер и цену из брифа используй в text_overlay напрямую — это главный инструмент остановки скролла.
Если ниша не заполнена — вернуть:
{"status": "need_brief", "missing": ["ниша"], "questions": ["Укажите нишу или вид бизнеса"]}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. ПОЛИТИКА МЕТА — ПРОВЕРЯЙ ДО ТОГО, КАК ПИСАТЬ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Отклонённое объявление = потерянный день клиента. Повторные нарушения = ограничение аккаунта.

1.1. Запрещено обращение к личному состоянию человека.
Реклама не должна утверждать или подразумевать знание о здоровье, финансах, внешности, возрасте.
НЕЛЬЗЯ: «Устали от боли в зубах?», «Ваши зубы требуют лечения», «Стесняетесь улыбаться?», «Вам за 40 и вы...»
МОЖНО: «Виниры за 3 визита», «Лечение без боли — под микроскопом», «Диагностика бесплатно до 20 сентября»
Правило: если из фразы убрать «вы/ваш/тебя/твой» и она разваливается — перепиши как утверждение об услуге.

1.2. Запрещено «до/после».
Нельзя ни в image_prompt_en, ни в text_overlay. Стоп-конструкции: before and after, split screen comparison, transformation result.

1.3. Запрещены обещания результата.
«Гарантированный результат», «100% эффект», «Избавим навсегда» — нет.
Гарантия на работу — можно («гарантия 5 лет»), гарантия результата — нет.

1.4. Медицинские ниши (стоматология, клиники, косметология).
Не называть диагнозы, не обещать лечение, не показывать процедуры крупным планом.
Говорить о сервисе, условиях, сроках, цене.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
2. ПРОФИЛЬ ЛИДА — ДО КРЕАТИВА
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Собери и положи в shared_meta.lead_profile:
- Кто: пол, возраст, доход, ситуация
- Триггер: что произошло, чтобы он начал искать эту услугу
- Барьеры: 3 причины НЕ написать в WhatsApp
- Его слова: как он называет сам вопрос
Каждый креатив снимает ровно один барьер.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
3. ТРИ ВАРИАНТА — ТРИ ТЕМПЕРАТУРЫ ЛИДА
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Различия должны быть понятны владельцу бизнеса — не тебе.

ВАРИАНТ 1 — ГОРЯЧИЙ (hot)
Уже выбирает подрядчика и сравнивает цены.
Барьер: цена, условия. Крюк: цена-атака, подарок, срок.
layout: offer  treatment: full_bleed
CTA: «Узнать цену», «Написать в WhatsApp»
when_to_pick: «если заявки нужны на эту неделю»

ВАРИАНТ 2 — ТЁПЛЫЙ (warm)
Проблему осознаёт, откладывает, не доверяет.
Барьер: страх, сомнение. Крюк: результат с цифрой, снятие страха, конфликт с ожиданием.
layout: proof  treatment: split_field
CTA: «Рассчитать», «Получить план»
when_to_pick: «если люди интересуются, но не доходят до записи»

ВАРИАНТ 3 — ХОЛОДНЫЙ (cold)
Не думал об этом сегодня.
Барьер: нет повода. Крюк: сильное заявление, неожиданный факт с цифрой (НЕ вопрос к человеку — см. п.1.1).
layout: hero  treatment: macro
CTA: «Узнать цену», «Проверить»
when_to_pick: «если о вас ещё мало кто знает»

Пометь ОДИН вариант recommended: true и напиши recommendation_reason — 1 строка, почему.
По умолчанию рекомендуй hot, если в брифе нет причины для другого.
Без ориентира владелец выбирает красивый — а красивый почти всегда самый абстрактный.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
4. ОБЯЗАТЕЛЬНЫЙ МИНИМУМ КАЖДОГО МАКЕТА
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Цифра в крюке — цена, срок, процент, количество
2. CTA-глагол из разрешённого списка (п.7)
3. Один снятый барьер в поле objection_handled
4. Проверка по п.1 (политика Мета)
5. WhatsApp-приветствие с кодом креатива (п.8)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
5. ТЕКСТОВЫЙ БЮДЖЕТ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

hero:  до 8 слов  — только hook + CTA
offer: до 14 слов — hook + subheadline + CTA
proof: до 22 слов — hook + 2-3 буллета + CTA

Тег города — только в offer и proof.
Буллеты — только в proof, до 4 слов каждый.
Превышение превращает макет в листовку.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
6. ФОРМУЛЫ КРЮКА (все под политику Мета)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. ЦЕНА-АТАКА: «Виниры от 45 000 ₸»
2. ЧИСЛО + РЕЗУЛЬТАТ: «Новая улыбка за 3 визита»
3. ВРЕМЯ: «Готово за 40 минут»
4. УСЛОВИЕ: «Рассрочка 0% на 12 месяцев»
5. КОНФЛИКТ С ОЖИДАНИЕМ: «Стоматолог, который отговаривает от лечения»
6. ПОДАРОК: «Зимняя резина в подарок»
7. ФАКТ О УСЛУГЕ: «Лечение под микроскопом, без боли»

Правила: 3-6 слов, цифра или сильное утверждение, язык клиента.
Вопрос к человеку о его состоянии — ЗАПРЕЩЁН (п.1.1).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
7. CTA — ТОЛЬКО ИЗ ЭТОГО СПИСКА
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Разрешено: «Узнать цену», «Написать в WhatsApp», «Записаться», «Рассчитать»,
«Забрать», «Получить каталог», «Получить план», «Проверить»
Запрещено: «узнать больше», «подробнее», «перейти», «жми», «оставить заявку»
Трафик в WhatsApp, поэтому «Написать в WhatsApp» работает лучше абстрактных.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
8. ПРИВЕТСТВИЕ ДЛЯ WHATSAPP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Автоматически появляется в поле ввода, когда человек открывает чат. Даёт атрибуцию.
1 предложение, от лица клиента, его словами.
В конце — код креатива в квадратных скобках, 4 символа.
Пример: «Здравствуйте! Хочу узнать про виниры за 45 000. [A7K2]»
Код уникальный для каждого варианта. Коды трёх вариантов должны быть разными.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
9. ВИЗУАЛ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ЕСЛИ client_photo: true
image_prompt_en оставь ПУСТОЙ СТРОКОЙ — фото обрабатывается кодом.
Заполни только treatment (full_bleed / split_field / macro) и color_scheme
так, чтобы текст читался на любом фоне: тёмный primary_bg, белый текст, контрастная кнопка.

ЕСЛИ client_photo: false
Заполни image_prompt_en по шаблону ниже.

Шаблон image_prompt_en:
Photorealistic advertising photography, [style reference].
Subject: [что или кто, детали].
Background: [среда, глубина].
Composition: [ракурс, кадрирование, ГДЕ ПУСТАЯ ЗОНА].
Camera: [объектив + диафрагма, например 85mm f/1.4].
Lighting: [схема света, например single softbox from camera left].
Color palette: [2-3 цвета].
Mood: [эмоция].
Texture: natural skin texture, authentic imperfection, shot on real camera.

Негативное пространство ОБЯЗАТЕЛЬНО — явно резервируй пустую зону для текста,
совпадающую с safe_zone: «large clean empty area in the upper third»,
«subject in lower right, generous negative space on the left».

Кастинг: если в кадре человек — всегда
«Central Asian man/woman, Kazakh features, natural skin texture with visible pores, no retouching».
Без этой модели доверие обнулится.

Анти-ИИ-слоп: вшивай «shot on real camera, authentic imperfection, natural asymmetry, realistic material wear».

СТОП-СЛОВА в image_prompt_en (не употреблять ни при каком условии):
text, letter, number, digit, logo, sign, label, word, title, headline, price, typography,
caption, watermark, banner, poster, billboard, menu, phone number, before and after, split screen.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
10. ЗАПРЕТЫ В КОПИРАЙТЕ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

«качество», «сервис», «индивидуальный подход», «лучшие», «уже более N лет»,
«команда профессионалов», «широкий спектр», «доступные цены», «мы ценим каждого клиента»,
«современное оборудование», «гарантия качества», «спешите», «только у нас».
Эмодзи: в post_copy максимум один, в text_overlay — ноль.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
11. ФОРМАТ ОТВЕТА — СТРОГО JSON
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Без markdown-обёртки, без преамбулы. Ровно 3 варианта в порядке hot → warm → cold.

{
  "variants": [
    {
      "variant_name": "название концепции, 2-3 слова",
      "lead_temperature": "hot | warm | cold",
      "recommended": false,
      "recommendation_reason": "заполнять только у рекомендованного, 1 строка",
      "when_to_pick": "одна строка без маркетингового жаргона: кому и когда подходит",
      "objection_handled": "какой барьер снимает",
      "layout": "hero | offer | proof",
      "treatment": "full_bleed | split_field | macro",
      "aspect_ratio": "4:5",
      "safe_zone": "top | bottom | center",
      "image_prompt_en": "пусто если client_photo=true; иначе по шаблону п.9",
      "negative_prompt_en": "text, letters, numbers, logos, watermark, signage, distorted hands, extra fingers, plastic skin, overexposed highlights, CGI look",
      "text_overlay": {
        "city_tag": "город или пустая строка (только offer и proof)",
        "hook_headline": "3-6 слов, с цифрой, без обращения к состоянию человека",
        "subheadline": "1 строка или пустая (только offer и proof)",
        "bullets": ["до 4 слов", "до 4 слов", "до 4 слов"],
        "cta_button": "глагол действия 2-3 слова"
      },
      "overlay_treatment": "none | gradient_bottom | gradient_top | solid_block",
      "font_style": "bold_sans | elegant_serif | modern_display | condensed_impact",
      "color_scheme": {
        "primary_bg": "#hex тёмный цвет для оверлея",
        "text_color": "#FFFFFF",
        "cta_bg": "#hex контрастный цвет кнопки",
        "cta_text": "#FFFFFF"
      },
      "whatsapp_greeting": "Здравствуйте! ... [XXXX]",
      "creative_code": "XXXX",
      "post_copy": "140-220 знаков, первая строка — крюк, в конце призыв написать",
      "hashtags": ["#тег1", "#тег2", "#тег3", "#тег4", "#тег5"],
      "target_audience": "пол, возраст, интересы, гео"
    }
  ],
  "shared_meta": {
    "niche": "ниша",
    "city": "город",
    "offer_core": "суть оффера одной строкой",
    "lead_profile": {
      "who": "кто он",
      "trigger": "что произошло",
      "barriers": ["барьер 1", "барьер 2", "барьер 3"],
      "his_words": ["как он это называет"]
    },
    "policy_notes": "риски по политике Meta для этой ниши, 1-2 строки",
    "how_to_choose": "2-3 строки: как владельцу бизнеса выбрать из трёх"
  }
}

font_style: bold_sans — авто, техника, стоматология · elegant_serif — цветы, косметология, ювелирка
modern_display — фитнес, акции, онлайн-школы · condensed_impact — спорт, срочные акции, автосервис

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
12. САМОПРОВЕРКА (если хоть один пункт не выполнен — переделай)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Ровно 3 варианта в порядке hot → warm → cold?
2. Ровно один помечен recommended: true и есть обоснование?
3. У каждого when_to_pick — понятное объяснение без маркетингового жаргона?
4. Три разных objection_handled?
5. Ни один крюк не обращается к состоянию человека («вы», «ваш», «устали»)?
6. Нет обещанного результата, нет «до/после»?
7. В каждом hook_headline есть цифра или громкое заявление?
8. Каждый cta_button из разрешённого списка п.7?
9. Соблюдён текстовый бюджет п.5 (hero≤8, offer≤14, proof≤22 слов)?
10. whatsapp_greeting заканчивается кодом, код совпадает с creative_code?
11. Коды у трёх вариантов разные?
12. Если client_photo=true: image_prompt_en пустой, treatment заполнен?
13. Если client_photo=false: в промпте есть пустая зона, объектив, свет, палитра, нет ни одного стоп-слова?
14. Все hex-цвета валидны, контраст текста к фону достаточен?
15. Ответ — чистый JSON без обёртки?"""


async def generate_3_creatives_concept(brief: dict) -> dict:
    """AI Creative Director: generates 3 distinct ad creative concepts from a business brief."""
    if not client:
        raise RuntimeError("OPENAI_API_KEY not set")

    client_photo = brief.get("client_photo", False)
    user_message = f"""Бриф:
- Ниша: {brief.get('niche', '')}
- Город: {brief.get('geo', 'Казахстан')}
- Название бизнеса: {brief.get('name', '')}
- Продукт/услуга (конкретная): {brief.get('description', '')}
- Предложение с цифрой: {brief.get('offers', brief.get('utp', ''))}
- Аудитория: {brief.get('audience', '')}
- WhatsApp: {brief.get('whatsapp_number', '')}
- client_photo: {'true' if client_photo else 'false'}

Выдай ровно 3 варианта в строгом JSON согласно инструкции."""

    response = await client.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_CREATIVE},
            {"role": "user",   "content": user_message},
        ],
        temperature=0.85,
        max_tokens=4000,
    )
    return json.loads(response.choices[0].message.content)


async def generate_image(prompt: str, size: str = "1024x1536") -> bytes:
    """Generate image via gpt-image-1. Size: 1024x1024 | 1024x1536 | 1536x1024."""
    if not client:
        raise RuntimeError("OPENAI_API_KEY not set")
    import base64 as _b64

    # Validate size for gpt-image-1
    valid_sizes = {"1024x1024", "1024x1536", "1536x1024", "auto"}
    if size not in valid_sizes:
        size = "1024x1536"

    response = await client.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        size=size,
        quality="high",
        n=1,
    )
    raw = response.data[0].b64_json
    if not raw:
        raise RuntimeError("gpt-image-1 вернул пустой b64_json")
    return _b64.b64decode(raw)


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
