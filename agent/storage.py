import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STORE_PATH = Path(__file__).resolve().parent.parent / "data" / "saved_routes.json"


def _load() -> list[dict]:
    if not STORE_PATH.exists():
        return []
    try:
        return json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def _save(items: list[dict]) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_route(
    slots: dict[str, Any],
    hotels: list[dict],
    chosen: dict | None = None,
    note: str = "",
) -> dict:
    """Сохраняет маршрут со всеми признаками. Позже тот же dict уйдёт в БД."""
    items = _load()
    record = {
        "id": len(items) + 1,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "note": note,
        "slots": slots,          # origin, destination, dates, budget, travelers, transport, preferences
        "options": hotels,       # что показали
        "chosen": chosen,        # что юзер выбрал (если есть)
    }
    items.append(record)
    _save(items)
    return record


def list_routes() -> list[dict]:
    return _load()