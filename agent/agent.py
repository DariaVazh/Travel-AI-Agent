import json
import re
import uuid

from llm import extract_slots, reply_to_user
from schema import TravelSlots
from slots import mark_ready, needs_clarification
from storage import save_route, list_routes


class TravelAgent:
    def __init__(self, user_id: str = "default"):
        self.slots = TravelSlots()
        self.last_plan = None
        self.user_id = user_id
        self.session_id = f"rt_{uuid.uuid4().hex[:10]}"
        # Улучшенная память: хранение истории диалога сессии
        self.chat_history = []
        # Сюда внешняя программа может положить свежий JSON с маршрутами
        self.external_packages = []

    def feed_external_routes(self, packages: list | dict):
        """Метод для внешней программы, которая скидывает JSON с маршрутами."""
        if isinstance(packages, dict):
            packages = [packages]
        self.external_packages = packages
        self.last_plan = {"packages": packages}

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

        # Добавляем сообщение пользователя в историю памяти
        self.chat_history.append({"role": "user", "content": text})
        # Ограничим историю последними 10 сообщениями, чтобы не раздувать контекст
        if len(self.chat_history) > 10:
            self.chat_history = self.chat_history[-10:]

        # Обработка команды бронирования
        is_book = any(
            w in text_l for w in ("бронь", "брон", "оформи", "оформл", "покупа", "беру", "выбираю", "заброни")
        )
        if is_book:
            packages = self.external_packages or (self.last_plan or {}).get("packages") or []
            if not packages:
                answer = "Пока нет готовых маршрутов для бронирования. Дождитесь загрузки данных или опишите пожелания."
                self.chat_history.append({"role": "assistant", "content": answer})
                return answer

            chosen = packages[0]  # берем первый или ищем по тексту
            chosen = dict(chosen)
            chosen["selected"] = True
            rec = self._autosave(note="book", package=chosen, chosen=chosen)

            answer = f"Готово! Маршрут успешно забронирован и сохранен (сессия #{rec['route_id']})."
            self.chat_history.append({"role": "assistant", "content": answer})
            return answer

        if text_l in {"мои маршруты", "сохранённые"}:
            routes = list_routes(user_id=self.user_id)
            if not routes:
                answer = "Пока ничего не сохранено."
            else:
                lines = []
                for r in routes[-5:]:
                    pkg = r.get("package") or r.get("chosen") or {}
                    dest = pkg.get("destination", {})
                    city = dest.get("city") if isinstance(dest, dict) else str(dest)
                    lines.append(f"#{r.get('route_id')}: {city or 'Маршрут'}")
                answer = "\n".join(lines)
            self.chat_history.append({"role": "assistant", "content": answer})
            return answer

        # Извлечение слотов (нейросеть понимает контекст и шутки)
        raw = extract_slots(user_text, self.slots.model_dump())
        if raw:
            incoming = TravelSlots.model_validate(raw)
            self.slots = mark_ready(self.slots.merge(incoming))

        # Формируем контекст для генерации ответа LLM
        context = {
            "slots": self.slots.model_dump(),
            "chat_history": self.chat_history,
            "available_packages": self.external_packages,
        }

        full = reply_to_user(user_text, context)
        if not full:
            full = "Я внимательно слушаю! Чем могу помочь с вашей поездкой?"

        self.chat_history.append({"role": "assistant", "content": full})
        self._autosave(note="turn")
        return full
