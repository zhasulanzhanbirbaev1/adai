import json
import os
from openai import AsyncOpenAI

_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", "")) if os.getenv("OPENAI_API_KEY") else None


async def generate_welcome_messages(niche: str, offer: str = "", city: str = "Казахстан") -> list[str]:
    """Generate 3 WhatsApp greeting variants for click-to-WhatsApp ads.

    Each message ends with a 4-char attribution code so the business owner
    can identify which creative brought the lead directly in WhatsApp chat.
    """
    if not _client:
        return [f"Здравствуйте! Хочу узнать про {niche}. [A001]"]

    prompt = f"""Ты пишешь короткие приветственные сообщения для WhatsApp-рекламы.
Сообщение автоматически появляется в поле ввода WhatsApp, когда человек нажимает на рекламу.
Пишешь от лица клиента — как будто ОН написал это сам.

Ниша: {niche}
Оффер: {offer or niche}
Город: {city}

Правила:
- 1 предложение, живой разговорный язык
- Конкретно, не абстрактно ("Хочу узнать цену на чистку зубов" — хорошо, "Хочу узнать подробнее" — плохо)
- В конце — уникальный 4-символьный код в квадратных скобках (буквы+цифры) для атрибуции
- Коды у трёх вариантов РАЗНЫЕ
- Не начинать с "Я"

Верни СТРОГО JSON:
{{"messages": ["вариант 1 [КОД1]", "вариант 2 [КОД2]", "вариант 3 [КОД3]"]}}"""

    response = await _client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200,
        response_format={"type": "json_object"},
    )
    data = json.loads(response.choices[0].message.content)
    return data.get("messages", [f"Здравствуйте! Хочу узнать про {niche}. [A001]"])
