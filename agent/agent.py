import json
import uuid

from llm import extract_slots, reply_to_user, extract_user_profile
from schema import TravelSlots, UserProfile
from slots import mark_ready
from storage import save_route, list_routes


class TravelAgent:
    def __init__(self, user_id: str = "default"):
        self.slots = TravelSlots()
        self.last_plan = None
        self.user_id = user_id
        self.session_id = f"rt_{uuid.uuid4().hex[:10]}"
        self.chat_history = []
        self.external_packages = []
        # Храним текущий профиль пользователя
        self.user_profile = UserProfile(user_id=user_id).model_dump()

    def feed_external_routes(self, packages: list | dict):
        """Метод для внешней программы, которая скидывает JSON с маршрутами."""
        if isinstance(packages, dict):
            packages = [packages]
        self.external_packages = packages
        self.last_plan = {"packages": packages}

    def get_user_profile_json(self) -> dict:
        """Метод для получения итогового JSON профиля пользователя."""
        raw_profile = extract_user_profile(
            user_id=self.user_id,
            chat_history=self.chat_history,
            current_profile=self.user_profile,
        )
        self.user_profile = UserProfile.model_validate(raw_profile).model_dump()
        return self.user_profile

    def _autosave(self, note: str, package: dict | None = None, chosen: dict | None = None):
        packages = self.external_packages or (self.last_plan or {}).get("packages") or []
        if package is None and packages:
            package = packages[0]
        if package is not None and not isinstance(package, dict):
            package = None

        if package is None:
            package = {
                "package_id": self.session_id,
                "query_raw": note,
                "origin": self.slots.origin,
                "destination": {"city": self.slots.destination},
                "packages": packages,
            }
        else:
            package = dict(package)
            package["package_id"] = self.session_id
            package["packages"] = packages

        # Сохраняем сессию вместе с обновленным профилем пользователя
        return save_route(
            self.slots.model_dump(),
            hotels=[],
            chosen=chosen or package,
            note=note,
            user_id=self.user_id,
            package=package,
            route_id=self.session_id,
        )

    def handle(self, user_text: str) -> str:
        text = user_text.strip()
        text_l = text.lower()

        self.chat_history.append({"role": "user", "content": text})
        if len(self.chat_history) > 10:
            self.chat_history = self.chat_history[-10:]

        # Бронирование
        is_book = any(
            w in text_l for w in ("бронь", "брон", "оформи", "оформл", "покупа", "беру", "выбираю", "заброни")
        )
        if is_book:
            packages = self.external_packages or (self.last_plan or {}).get("packages") or []
            if not packages:
                answer = "Пока нет готовых маршрутов для бронирования."
                self.chat_history.append({"role": "assistant", "content": answer})
                return answer

            chosen = dict(packages[0])
            chosen["selected"] = True
            rec = self._autosave(note="book", package=chosen, chosen=chosen)

            answer = f"Готово! Маршрут забронирован (сессия #{rec['route_id']})."
            self.chat_history.append({"role": "assistant", "content": answer})
            return answer

        if text_l in {"мои маршруты", "сохранённые"}:
            routes = list_routes(user_id=self.user_id)
            if not routes:
                answer = "Пока ничего не сохранено."
            else:
                lines = [f"#{r.get('route_id')}: {r.get('chosen', {}).get('destination', {}).get('city', 'Маршрут')}" for r in routes[-5:]]
                answer = "\n".join(lines)
            self.chat_history.append({"role": "assistant", "content": answer})
            return answer

        # Слоты
        raw = extract_slots(user_text, self.slots.model_dump())
        if raw:
            incoming = TravelSlots.model_validate(raw)
            self.slots = mark_ready(self.slots.merge(incoming))

        context = {
            "slots": self.slots.model_dump(),
            "chat_history": self.chat_history,
            "available_packages": self.external_packages,
        }

        full = reply_to_user(user_text, context)
        if not full:
            full = "Я на связи! Чем помочь с поездкой?"

        self.chat_history.append({"role": "assistant", "content": full})

        # Обновляем профиль пользователя после реплики
        self.get_user_profile_json()

        self._autosave(note="turn")
        return full
