import json
import re
from openai import OpenAI, APIError, RateLimitError

from config import (
    APP_TITLE,
    HTTP_REFERER,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    OPENROUTER_MODEL,
)

def get_client() -> OpenAI:
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
Если пользователь шутит или пишет не по делу, intent установи как 'smalltalk'.
"""

SYSTEM_REPLY = """Ты — дружелюбный travel-агент. Твоя задача — общаться с пользователем, очеловечивать готовые данные маршрутов и отелей (из JSON в контексте) и отвечать с эмодзи.

Правила:
1. Если пользователь шутит или отвлекается — ответь вежливо/с юмором, но мягко верни к выбору поездки.
2. Не придумывай цены из головы — опирайся строго на переданные packages.
3. Задавай не более одного уточняющего вопроса в конце.
"""

SYSTEM_PROFILE_EXTRACT = """Ты — модуль извлечения долговременного профиля пользователя.
На основе истории общения сформируй JSON профиля пользователя по строгой структуре:
{
  "schema_version": 1,
  "user_id": "...",
  "home_city": "...",
  "search_defaults": {
    "transport": "plane/train/any",
    "max_transfers": 0,
    "hotel_min_stars": 4,
    "free_cancellation": false,
    "pets": false,
    "priority": {"price": 0.5, "time": 0.5}
  },
  "hotel_preferences": {
    "breakfast": false,
    "amenities": [],
    "location": []
  },
  "interests": [],
  "dislikes": [],
  "notes": []
}
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

    try:
        resp = client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_EXTRACT},
                {"role": "user", "content": user_text + extra},
            ],
            temperature=0.2,
        )
        return parse_json(resp.choices[0].message.content or "{}")
    except (RateLimitError, APIError) as e:
        print(f"[Предупреждение LLM Slot Extraction]: {e}")
        return previous_slots or {}
    except Exception as e:
        print(f"[Ошибка Slot Extraction]: {e}")
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
                    "content": f"Сообщение пользователя: {user_text}\n\nКонтекст и данные маршрутов:\n{json.dumps(context, ensure_ascii=False)}",
                },
            ],
            temperature=0.5,
        )
        return (resp.choices[0].message.content or "").strip()
    except RateLimitError:
        # Резервный ответ при превышении лимита бесплатной модели
        packages = context.get("available_packages", [])
        if packages:
            pkg_list = packages if isinstance(packages, list) else packages.get("packages", [])
            if pkg_list:
                cheapest = min(pkg_list, key=lambda x: x.get("totals", {}).get("grand", 999999))
                title = cheapest.get("title", "Самый доступный вариант")
                price = cheapest.get("totals", {}).get("grand", 0)
                hotel = cheapest.get("hotel", {}).get("name", "")
                return f"⚠️ *(Достигнут дневной лимит запросов к AI)*\n\nТем не менее, судя по загруженным данным, самый дешевый вариант — **«{title}»** ({hotel}) за **{price} ₽**!"
        return "⚠️ Достигнут дневной лимит запросов к нейросети (Rate Limit). Попробуйте чуть позже или смените модель в .env."
    except APIError as e:
        return f"Произошла ошибка при обращении к нейросети: {e.message}"
    except Exception as e:
        return f"Не удалось обработать ответ: {e}"

def extract_user_profile(user_id: str, chat_history: list, current_profile: dict | None = None) -> dict:
    client = get_client()
    extra = ""
    if current_profile:
        extra = f"\n\nТекущий профиль:\n{json.dumps(current_profile, ensure_ascii=False)}"

    try:
        resp = client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROFILE_EXTRACT},
                {
                    "role": "user",
                    "content": f"User ID: {user_id}\nИстория диалога:\n{json.dumps(chat_history, ensure_ascii=False)}{extra}",
                },
            ],
            temperature=0.2,
        )
        data = parse_json(resp.choices[0].message.content or "{}")
        data["user_id"] = user_id
        return data
    except Exception as e:
        print(f"[Предупреждение Profile Extraction]: {e}")
        return current_profile or {"schema_version": 1, "user_id": user_id}
