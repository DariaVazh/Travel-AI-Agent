import os
from dotenv import load_dotenv
from .slots_schema import TravelSlots

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv(
    "OPENROUTER_MODEL",
    "meta-llama/llama-3.3-70b-instruct:free",
)
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

HTTP_REFERER = os.getenv("HTTP_REFERER", "http://localhost:3000")
APP_TITLE = os.getenv("APP_TITLE", "Ostrovok Travel Agent")


def slots_to_query(slots: TravelSlots) -> dict:
    total = (slots.travelers.adults or 1) + (slots.travelers.children or 0) + (slots.travelers.infants or 0)
    modes = slots.transport.modes or ["any"]
    transport = "any" if "any" in modes else modes[0]

    budget = None
    if slots.budget.amount is not None:
        budget = slots.budget.amount * total if slots.budget.per_person else slots.budget.amount

    return {
        "origin": slots.origin,
        "destination": slots.destination,
        "date_from": slots.dates.date_from,
        "date_to": slots.dates.date_to,
        "budget": budget,
        "transport": transport,
        "adults": slots.travelers.adults or 1,
        "children": slots.travelers.children or 0,
        "pets": slots.preferences.pets,
        "max_transfers": None,
        "hotel_min_stars": slots.preferences.hotel_stars_min or 0,
        "free_cancellation": False,
        "priority": {"price": 0.6, "time": 0.4},
    }