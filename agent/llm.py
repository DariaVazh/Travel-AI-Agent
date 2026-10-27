import json
import re
from pydantic import ValidationError
from openai import OpenAI, APIError, RateLimitError
from .llm_config import (
    APP_TITLE,
    HTTP_REFERER,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    OPENROUTER_MODEL,
)
from .slots_schema import TravelSlots

def get_client() -> OpenAI:
    return OpenAI(
        api_key=OPENROUTER_API_KEY or "dummy_key",
        base_url=OPENROUTER_BASE_URL,
        default_headers={
            "HTTP-Referer": HTTP_REFERER,
            "X-Title": APP_TITLE,
        },
    )

SYSTEM_EXTRACT = f"""Ты — модуль анализа намерений. Выдели слоты из сообщения пользователя.
Ответ ДОЛЖЕН быть строго в формате JSON, соответствующем этой Pydantic-схеме:
{json.dumps(TravelSlots.model_json_schema(), ensure_ascii=False, indent=2)}

Важные правила:
1. Даты должны быть в формате YYYY-MM-DD и не должны быть раньше сегодняшнего дня.
2. Массив transport.modes может содержать ТОЛЬКО значения: "plane", "train", "any".
3. Если какое-то поле неизвестно, ставь null или значение по умолчанию.
"""

SYSTEM_REPLY = """Ты — дружелюбный travel-агент. Твоя задача — очеловечивать готовые данные маршрутов, переданные из API (в JSON), и отвечать с эмодзи.
Не придумывай цены из головы. Отвечай коротко и понятно.
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
    extra = f"\n\nТекущие слоты:\n{json.dumps(previous_slots, ensure_ascii=False)}" if previous_slots else ""

    try:
        resp = client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_EXTRACT},
                {"role": "user", "content": user_text + extra},
            ],
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        data = parse_json(resp.choices[0].message.content or "{}")
        validated = TravelSlots.model_validate(data)
        return validated.model_dump()
    except (ValidationError, json.JSONDecodeError, RateLimitError, APIError) as e:
        print(f"[Slots Extraction Warning/Error]: {e}")
        return previous_slots or {}

def reply_to_user(user_text: str, context: dict) -> str:
    client = get_client()
    try:
        resp = client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_REPLY},
                {
                    "role": "user",
                    "content": f"Сообщение пользователя: {user_text}\n\nAPI данные:\n{json.dumps(context, ensure_ascii=False)}",
                },
            ],
            temperature=0.4,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        return "Вот подобранные варианты путешествия по вашему запросу! 👇"