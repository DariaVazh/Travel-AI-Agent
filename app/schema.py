"""Контракт JSON между LLM (Даша), поиском (Настя), ботом (Соня) и БД (Денис)."""
from datetime import date

REQUIRED = ("origin", "destination", "date_from")
MAX_TRIP_DAYS = 60

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


def _num(value, cast, name, errors, default):
    try:
        return cast(value)
    except (TypeError, ValueError):
        errors.append(f"{name}: ожидается число")
        return default


def normalize_query(raw: dict, today=None):
    """Возвращает (query, missing, errors).
    missing -> поля, о которых LLM должна спросить пользователя.
    errors  -> поля, где значение некорректно (тоже повод переспросить)."""
    today = today or date.today()
    q = {**DEFAULTS, **{k: v for k, v in (raw or {}).items() if k in DEFAULTS}}
    missing = [k for k in REQUIRED if not q.get(k)]
    errors = []

    d1, d2 = _parse(q["date_from"]), _parse(q["date_to"])
    if q["date_from"] and d1 is None:
        errors.append("date_from: ожидается YYYY-MM-DD")
    if q["date_to"] and d2 is None:
        errors.append("date_to: ожидается YYYY-MM-DD")
    if d1 and d1 < today:
        errors.append("date_from: дата уже прошла")
    if d1 and d2 and d2 < d1:
        errors.append("date_to раньше date_from")
    if d1 and d2 and (d2 - d1).days > MAX_TRIP_DAYS:
        errors.append(f"поездка длиннее {MAX_TRIP_DAYS} дней: проверьте даты")

    q["transport"] = str(q["transport"] or "any").lower()
    if q["transport"] not in ("plane", "train", "any"):
        errors.append("transport: plane | train | any")

    q["adults"] = _num(q["adults"], int, "adults", errors, 1)
    q["children"] = _num(q["children"], int, "children", errors, 0)
    if q["adults"] < 1:
        errors.append("adults: нужен хотя бы один взрослый")
    if q["children"] < 0:
        errors.append("children: не может быть отрицательным")
    if q["budget"] is not None:
        q["budget"] = _num(q["budget"], float, "budget", errors, None)
        if q["budget"] is not None and q["budget"] <= 0:
            errors.append("budget: должен быть больше нуля")
    if q["max_transfers"] is not None:
        q["max_transfers"] = _num(q["max_transfers"], int, "max_transfers", errors, None)
    q["hotel_min_stars"] = _num(q["hotel_min_stars"], int, "hotel_min_stars", errors, 0)
    if not 0 <= q["hotel_min_stars"] <= 5:
        errors.append("hotel_min_stars: от 0 до 5")
    q["pets"], q["free_cancellation"] = bool(q["pets"]), bool(q["free_cancellation"])

    if q["origin"] and q["destination"] and \
            str(q["origin"]).strip().lower() == str(q["destination"]).strip().lower():
        errors.append("origin и destination совпадают")

    p = {**DEFAULTS["priority"], **(q["priority"] or {})}
    try:
        wp, wt = max(float(p["price"]), 0.0), max(float(p["time"]), 0.0)
    except (TypeError, ValueError):
        wp, wt = 0.5, 0.5
    total = (wp + wt) or 1.0
    q["priority"] = {"price": wp / total, "time": wt / total} if (wp + wt) else dict(DEFAULTS["priority"])
    q["nights"] = (d2 - d1).days if d1 and d2 else 0
    q["guests"] = q["adults"] + max(q["children"], 0)
    return q, missing, errors
