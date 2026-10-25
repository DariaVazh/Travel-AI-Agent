import re
from llm import extract_slots, reply_to_user
from schema import TravelSlots
from slots import mark_ready, needs_clarification
from tools import inspire_destinations, mock_checkout, search_hotels
from storage import save_route, list_routes


def _find_hotel(fragment: str, hotels: list[dict]) -> dict | None:
    if not fragment or not hotels:
        return None
    p = fragment.lower().strip()
    for h in hotels:
        name = h.get("name", "").lower()
        if p in name or name in p:
            return h
    # по словам
    for h in hotels:
        name = h.get("name", "").lower()
        if any(w in name for w in p.split() if len(w) > 3):
            return h
    return None


class TravelAgent:
    def __init__(self):
        self.slots = TravelSlots()
        self.last_plan: dict | None = None

    def handle(self, user_text: str) -> str:
        text = user_text.strip()
        text_l = text.lower()

        # ========== 1. БРОНЬ / ОФОРМИТЬ — ДО LLM ==========
        is_book = any(
            w in text_l
            for w in (
                "бронь",
                "брон",
                "оформи",
                "оформл",
                "покупа",
                "беру",
                "выбираю",
                "заброни",
            )
        )
        if is_book:
            hotels = (self.last_plan or {}).get("hotels") or []
            chosen = None

            # «оформить Riviera Park» / «бронь Riviera на ноябрь»
            m = re.search(
                r"(?:бронь|брон\w*|оформи\w*|заброни\w*|беру|выбираю)\s+(.+)",
                text,
                flags=re.I,
            )
            tail = m.group(1).strip() if m else ""
            # убрать «на ноябрь», «с 1 по 3»
            tail_clean = re.sub(
                r"\s+на\s+\S+.*$|\s+с\s+\d+.*$",
                "",
                tail,
                flags=re.I,
            ).strip()

            if tail_clean:
                chosen = _find_hotel(tail_clean, hotels)
            if not chosen and hotels:
                chosen = hotels[0]

            if not hotels:
                return (
                    "Пока нет списка отелей в этой сессии. "
                    "Напишите сначала «в Сочи с ребёнком», потом «бронь Riviera Park»."
                )

            # даты из фразы (грубо)
            if "ноябр" in text_l:
                self.slots.dates.month = "ноябрь"
            dm = re.search(r"с\s+(\d+)\s+по\s+(\d+)", text_l)
            if dm and self.slots.dates.month == "ноябрь":
                self.slots.dates.date_from = f"2026-11-{int(dm.group(1)):02d}"
                self.slots.dates.date_to = f"2026-11-{int(dm.group(2)):02d}"

            rec = save_route(
                self.slots.model_dump(),
                hotels,
                chosen=chosen,
                note="book_command",
            )
            name = chosen.get("name", "?") if chosen else "?"
            return (
                f"Готово. «{name}» сохранён как маршрут #{rec['id']}.\n"
                f"Файл: data/saved_routes.json\n"
                f"(Оплата имитирована.)"
            )

        if text_l in {"мои маршруты", "сохранённые"}:
            routes = list_routes()
            if not routes:
                return "Пока ничего не сохранено."
            lines = []
            for r in routes[-5:]:
                ch = r.get("chosen") or {}
                lines.append(f"#{r['id']}: {ch.get('name', '—')}")
            return "\n".join(lines)

        # ========== 2. ОБЫЧНЫЙ ДИАЛОГ ==========
        if "дешевле" in text_l and self.slots.budget.amount:
            self.slots.budget.amount = float(self.slots.budget.amount) * 0.8

        raw = extract_slots(user_text, self.slots.model_dump())
        incoming = TravelSlots.model_validate(raw)
        self.slots = mark_ready(self.slots.merge(incoming))

        question = needs_clarification(self.slots)
        if question:
            return question

        if not self.slots.destination:
            self.slots.intent = "inspire"
            self.slots.destination_flexible = True

        if self.slots.intent == "inspire" or not self.slots.destination:
            ideas = inspire_destinations(self.slots)
            return reply_to_user(
                user_text,
                {"slots": self.slots.model_dump(), "ideas": ideas},
            )

        options = search_hotels(self.slots)
        self.last_plan = {
            "destination": self.slots.destination
            or (options[0]["city"] if options else None),
            "dates": self.slots.dates.model_dump(),
            "hotels": options,
        }
        return reply_to_user(
            user_text,
            {"slots": self.slots.model_dump(), "options": options},
        )