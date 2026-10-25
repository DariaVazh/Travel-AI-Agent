"""Контракт JSON между LLM (Даша), поиском (Настя), ботом (Соня) и БД (Денис)."""
from datetime import date

REQUIRED = ("origin", "destination", "date_from")

DEFAULTS = {
    "origin": None,            # город вылета, str
    "destination": None,       # город прибытия, str
    "date_from": None,         # "YYYY-MM-DD"
    "date_to": None,           # "YYYY-MM-DD" или null (в одну сторону, без отеля)
    "budget": None,            # RUB на всю поездку; null = без ограничения
    "transport": "any",        # "plane" | "train" | "any"
    "adults": 1,
    "children": 0,
    "pets": False,
    "max_transfers": None,     # null = без ограничения
    "hotel_min_stars": 0,
    "free_cancellation": False,  # жёсткое требование к отелю
    "priority": {"price": 0.5, "time": 0.5},  # что важнее пользователю
}


def _parse(d):
    try:
        return date.fromisoformat(d)
    except (TypeError, ValueError):
        return None


def normalize_query(raw: dict):
    """Возвращает (query, missing, errors).
    missing -> список полей, о которых LLM должна спросить пользователя."""
    q = {**DEFAULTS, **{k: v for k, v in (raw or {}).items() if k in DEFAULTS}}
    missing = [k for k in REQUIRED if not q.get(k)]
    errors = []

    d1, d2 = _parse(q["date_from"]), _parse(q["date_to"])
    if q["date_from"] and d1 is None:
        errors.append("date_from: ожидается YYYY-MM-DD")
    if q["date_to"] and d2 is None:
        errors.append("date_to: ожидается YYYY-MM-DD")
    if d1 and d2 and d2 < d1:
        errors.append("date_to раньше date_from")
    if q["transport"] not in ("plane", "train", "any"):
        errors.append("transport: plane | train | any")

    p = {**DEFAULTS["priority"], **(q["priority"] or {})}
    total = (p["price"] + p["time"]) or 1
    q["priority"] = {"price": p["price"] / total, "time": p["time"] / total}
    q["nights"] = (d2 - d1).days if d1 and d2 else 0
    q["guests"] = int(q["adults"]) + int(q["children"])
    return q, missing, errors
