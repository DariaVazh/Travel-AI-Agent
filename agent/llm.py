import json
import re
from openai import OpenAI

from config import (
    APP_TITLE,
    HTTP_REFERER,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    OPENROUTER_MODEL,
)

SYSTEM_EXTRACT = """Правила:
- Не выдумывай точные даты и суммы, если их не было.
- Если направления нет, но есть «море/тепло/отдых» — destination_flexible=true, intent=inspire, ready_to_search=true.
- Если мало данных — ВСЁ РАВНО ready_to_search=true и clarifying_question=null.
- clarifying_question ставь ТОЛЬКО если сообщение пустое по смыслу (нет ни места, ни месяца, ни типа отдыха).
- Не задавай больше одного вопроса; лучше null.
- intent: inspire, если город неизвестен; search — если город есть.
"""

SYSTEM_REPLY = """Ты travel-агент Островка. Стиль: сначала польза, потом один мягкий вопрос (необязательно).
Структура ответа:
1) 2–3 конкретных варианта (город/отель, цена, почему подходит)
2) Что можно сузить одной фразой: «если скажете месяц или потолок бюджета — сузим»
Не устраивай допрос. Не задавай несколько вопросов подряд. Не пиши «уточните даты, бюджет и состав»."""


def get_client() -> OpenAI:
    if not OPENROUTER_API_KEY:
        raise RuntimeError("Нет OPENROUTER_API_KEY в .env")
    return OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
        default_headers={
            "HTTP-Referer": HTTP_REFERER,
            "X-Title": APP_TITLE,
        },
    )


def parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"Модель не вернула JSON: {text[:200]}")
    return json.loads(m.group())


def extract_slots(user_text: str, previous_slots: dict | None = None) -> dict:
    client = get_client()
    extra = ""
    if previous_slots:
        extra = f"\n\nТекущие слоты (обнови, не обнуляй известное):\n{json.dumps(previous_slots, ensure_ascii=False)}"

    resp = client.chat.completions.create(
        model=OPENROUTER_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_EXTRACT},
            {"role": "user", "content": user_text + extra},
        ],
        temperature=0.2,
    )
    return parse_json(resp.choices[0].message.content or "")


def reply_to_user(user_text: str, context: dict) -> str:
    client = get_client()
    resp = client.chat.completions.create(
        model=OPENROUTER_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_REPLY},
            {
                "role": "user",
                "content": f"Сообщение пользователя: {user_text}\n\nКонтекст:\n{json.dumps(context, ensure_ascii=False)}",
            },
        ],
        temperature=0.4,
    )
    return (resp.choices[0].message.content or "").strip()