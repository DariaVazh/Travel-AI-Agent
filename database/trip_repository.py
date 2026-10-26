from database.connection import AsyncSessionLocal
from database.models import TripState
from datetime import datetime, timezone


async def save_search_result(user_id: int, result: dict):
    if result.get("status") not in ("ok", "no_results"):
        raise ValueError("Поиск ещё не дал результата")

    async with AsyncSessionLocal.begin() as session:

        state = await session.get(
            TripState,
            user_id,
            with_for_update=True
        )

        if state is None:
            state = TripState(user_id=user_id)
            session.add(state)

        state.query = result["query"]
        state.packages = result["packages"]

        # Новый поиск сбрасывает старый выбор
        state.selected_package_id = None

async def select_package(user_id: int, package_id: str):
    async with AsyncSessionLocal.begin() as session:

        state = await session.get(
            TripState,
            user_id,
            with_for_update=True
        )

        if state is None:
            raise ValueError("Нет активного поиска")

        found = any(
            p["id"] == package_id
            for p in state.packages
        )

        if not found:
            raise ValueError("Пакет не найден")

        state.selected_package_id = package_id


async def get_trip_state(user_id: int):
    async with AsyncSessionLocal() as session:
        state = await session.get(TripState, user_id)

        if state is None:
            return None

        return {
            "query": state.query,
            "packages": state.packages,
            "selected_package_id": state.selected_package_id,
            "cart": state.cart
        }


async def add_selected_to_cart(user_id: int):
    async with AsyncSessionLocal.begin() as session:

        state = await session.get(
            TripState,
            user_id,
            with_for_update=True
        )

        if state is None or not state.selected_package_id:
            raise ValueError("Пакет ещё не выбран")

        package = next(
            (
                p for p in state.packages
                if p["id"] == state.selected_package_id
            ),
            None
        )

        if package is None:
            raise ValueError("Выбранный пакет не найден")

        cart = dict(state.cart or {"items": []})
        items = list(cart.get("items", []))

        items.append({
            "package_id": package["id"],
            "package": package,
            "query": state.query,
            "added_at": datetime.now(
                timezone.utc
            ).isoformat()
        })

        state.cart = {**cart, "items": items}
