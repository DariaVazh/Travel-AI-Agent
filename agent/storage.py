import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROUTES_DIR = Path(__file__).resolve().parent.parent / "data" / "routes"
# если у тебя плоская структура (файлы рядом с main):
# ROUTES_DIR = Path(__file__).resolve().parent / "data" / "routes"


def _user_dir(user_id: str) -> Path:
    path = ROUTES_DIR / str(user_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_route(
    slots: dict[str, Any],
    hotels: list | None = None,
    chosen: dict | None = None,
    note: str = "",
    user_id: str = "default",
    package: dict | None = None,
    cart: dict | None = None,
    route_id: str | None = None,
) -> dict:
    """
    Один route_id = один файл.
    Повторный вызов с тем же route_id перезаписывает файл.
    """
    hotels = hotels or []

    if chosen is not None and not isinstance(chosen, dict):
        chosen = {"name": str(chosen)}
    if package is not None and not isinstance(package, dict):
        package = {"raw": str(package)}

    if route_id is None:
        if isinstance(package, dict) and package.get("package_id"):
            route_id = str(package["package_id"])
        else:
            route_id = f"rt_{uuid.uuid4().hex[:10]}"

    if isinstance(package, dict):
        package = {**package, "package_id": route_id}

    record = {
        "route_id": route_id,
        "user_id": str(user_id),
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "note": note,
        "slots": slots or {},
        "options": hotels,
        "chosen": chosen,
        "package": package,
        "cart": cart,
    }

    path = _user_dir(user_id) / f"{route_id}.json"
    path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    record["file"] = str(path)
    return record


def list_routes(user_id: str = "default") -> list:
    folder = _user_dir(user_id)
    out = []
    for path in sorted(folder.glob("*.json")):
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return out


def get_route(user_id: str, route_id: str) -> dict | None:
    path = _user_dir(user_id) / f"{route_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
