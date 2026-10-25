import json
from pathlib import Path

from schema import TravelSlots

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "mock_hotels.json"


def load_hotels() -> dict:
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def inspire_destinations(slots: TravelSlots) -> list[dict]:
    hotels = load_hotels()
    ideas = []
    for city, items in hotels.items():
        avg = sum(h["price"] for h in items) / len(items)
        if slots.budget.unlimited or slots.budget.amount is None or avg <= (slots.budget.amount or 10**9):
            why = []
            if slots.preferences.sea or slots.destination_flexible:
                why.append("подходит под запрос про море/отдых")
            if slots.preferences.with_child_friendly or slots.travelers.children:
                why.append("есть семейные варианты")
            ideas.append({"city": city, "avg_night_price": round(avg), "why": "; ".join(why) or "популярное направление"})
    return ideas[:3]


def score_hotel(hotel: dict, slots: TravelSlots) -> tuple[float, str]:
    score = 0.0
    reasons = []
    budget = slots.budget.amount

    if slots.budget.unlimited or budget is None:
        score += 1
    elif hotel["price"] <= budget:
        score += 2
        reasons.append("в бюджете")
    else:
        score -= 3
        reasons.append("дороже бюджета")

    if hotel.get("breakfast"):
        score += 1
        reasons.append("завтрак")
    if hotel.get("free_cancel"):
        score += 1
        reasons.append("бесплатная отмена")
    if slots.travelers.children and hotel.get("stars", 0) >= 4:
        score += 1
        reasons.append("удобно с детьми")
    if slots.preferences.hotel_stars_min and hotel.get("stars", 0) >= slots.preferences.hotel_stars_min:
        score += 1

    return score, ", ".join(reasons) or "базовый вариант"


def search_hotels(slots: TravelSlots) -> list[dict]:
    hotels = load_hotels()
    city = slots.destination
    if not city or city not in hotels:
        # гибкий поиск: все города
        pool = []
        for c, items in hotels.items():
            for h in items:
                pool.append({**h, "city": c})
    else:
        pool = [{**h, "city": city} for h in hotels[city]]

    ranked = []
    for h in pool:
        sc, reason = score_hotel(h, slots)
        ranked.append({**h, "score": sc, "reason": reason})
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked[:3]


def mock_checkout(plan: dict) -> dict:
    return {
        "status": "ok",
        "message": "Покупка имитирована (мок). Бронь не создавалась.",
        "plan": plan,
    }