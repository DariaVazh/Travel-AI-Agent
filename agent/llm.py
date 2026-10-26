import json
import re

from config import (
    APP_TITLE,
    HTTP_REFERER,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    OPENROUTER_MODEL,
)
from openai import OpenAI


def get_client() -> OpenAI:
    # Используем собранный ключ или плейсхолдер для защиты от аварийного завершения
    api_key = OPENROUTER_API_KEY if OPENROUTER_API_KEY else "dummy_key"

    return OpenAI(
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL,
        default_headers={
            "HTTP-Referer": HTTP_REFERER,
            "X-Title": APP_TITLE,
        },
    )

SYSTEM_EXTRACT = """Ты — модуль анализа намерений и извлечения параметров (слотов) поездки.
Внимательно читай сообщения пользователя и обновляй текущие слоты (направления, даты, бюджет, пожелания).
Если пользователь шутит или пишет не по делу (не связано с путешествиями), не затирай старые слоты, а intent установи как 'smalltalk'.
"""

SYSTEM_REPLY = """Ты — дружелюбный travel-агент. Твоя задача — общаться с пользователем, очеловечивать готовые данные маршрутов и отелей, которые приходят в контексте в виде JSON, и отвечать с эмодзи.

Правила поведения:
1. Если пользователь шутит, отвлекается или говорит на отвлеченные темы — поддержи шутку или ответь вежливо, но обязательно мягко верни к выбору поездки или обсуждению маршрута.
2. Если в контексте переданы готовые маршруты (packages) от внешней программы, представь их понятно, структурировано и привлекательно. Не придумывай цены и билеты из головы — опирайся строго на переданные данные.
3. Если пользователь просит забронировать или выбрать конкретный вариант — подтверди выбор.
4. Задавай не более одного уточняющего вопроса в конце.
"""

def parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {}
    return json.loads(m.group())

def extract_slots(user_text: str, previous_slots: dict | None = None) -> dict:
    client = get_client()
    extra = ""
    if previous_slots:
        extra = f"\n\nТекущие слоты:\n{json.dumps(previous_slots, ensure_ascii=False)}"

    resp = client.chat.completions.create(
        model=OPENROUTER_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_EXTRACT},
            {"role": "user", "content": user_text + extra},
        ],
        temperature=0.2,
    )
    try:
        return parse_json(resp.choices[0].message.content or "{}")
    except Exception:
        return {}

def reply_to_user(user_text: str, context: dict) -> str:
    client = get_client()
    resp = client.chat.completions.create(
        model=OPENROUTER_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_REPLY},
            {
                "role": "user",
                "content": f"Сообщение пользователя: {user_text}\n\nКонтекст и данные маршрутов:\n{json.dumps(context, ensure_ascii=False)}",
            },
        ],
        temperature=0.5,
    )
    return (resp.choices[0].message.content or "").strip()
