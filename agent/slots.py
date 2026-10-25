from schema import TravelSlots


def needs_clarification(slots: TravelSlots) -> str | None:
    """Спрашиваем только если вообще не за что зацепиться."""
    has_hook = (
        bool(slots.destination)
        or slots.destination_flexible
        or slots.preferences.sea
        or slots.preferences.warm
        or bool(slots.dates.month)
        or bool(slots.dates.date_from)
        or slots.budget.unlimited
        or slots.budget.amount is not None
        or slots.intent == "inspire"
    )
    if has_hook:
        return None  # не допрашиваем — идём предлагать
    # совсем пустой запрос вроде «привет» / «хочу отдохнуть»
    return "Могу сразу набросать идеи: море, город или горы? Или напишите месяц — подберу варианты."


def mark_ready(slots: TravelSlots) -> TravelSlots:
    data = slots.model_dump()
    # готовы искать/вдохновлять, если есть хоть один зацеп
    data["ready_to_search"] = needs_clarification(slots) is None
    data["clarifying_question"] = None  # не тащим вопрос из LLM в приоритет
    return TravelSlots.model_validate(data)