import asyncio
import uuid
from slots_schema import TravelSlots, UserProfile
import asyncio
import uuid
from .slots_schema import TravelSlots, UserProfile[cite: 12, 18]
from .llm import extract_slots, reply_to_user[cite: 12, 14]
from .llm_config import slots_to_query[cite: 12, 15]
from .storage import save_route, list_routes[cite: 12, 19]

# Обязательные импорты реальных функций из внешней папки app/
from app.search import plan_trip, replan, compare_destinations[cite: 12]
from app.cart import build_cart, mock_checkout[cite: 12]
from app.output import to_api, to_api_compare[cite: 12]

COVERAGE_CITIES = ["Сочи", "Москва", "Санкт-Петербург", "Казань", "Калининград"][cite: 12]

class TravelAgent:
    def __init__(self, user_id: str = "default"):
        self.slots = TravelSlots()[cite: 12, 18]
        self.user_id = user_id[cite: 12]
        self.session_id = f"rt_{uuid.uuid4().hex[:10]}"[cite: 12]
        self.chat_history = [][cite: 12]
        self.user_profile = UserProfile(user_id=user_id).model_dump()[cite: 12, 18]

        self.raw_res = None[cite: 12]
        self.active_cart = None[cite: 12]
        self.booking_state = None  # None | "awaiting_checkout_info"[cite: 12]

    def feed_external_routes(self, data: dict):
        """Принимает JSON с готовыми маршрутами от внешней программы."""
        self.raw_res = data

    def get_user_profile_json(self) -> dict:
        return self.user_profile

    async def handle_async(self, user_text: str) -> dict:
        text = user_text.strip()
        text_l = text.lower()
        self.chat_history.append({"role": "user", "content": text})

        # --- Пункт 4: Логика демо-бронирования ---
        if self.booking_state == "awaiting_checkout_info" and self.active_cart:
            traveler_info = {"raw_input": text}
            result = mock_checkout(self.active_cart, traveler_info)
            self.booking_state = None
            self.active_cart = None

            return {
                "text": f"✅ Оформлена **демо-бронь** (№ {result.get('order_id')}).\n"
                        f"Имитация оплаты прошла успешно. Настоящее бронирование не создавалось.",
                "buttons": []
            }

        # Выбор конкретного пакета по callback/id (например, pick:p643aa061)
        if text_l.startswith("pick:") or "выбираю" in text_l or "оформить" in text_l:
            pkg_id = text.split(":")[-1].strip() if ":" in text else None

            selected_package = None
            if self.raw_res and "packages" in self.raw_res:
                for pkg in self.raw_res["packages"]:
                    if pkg.get("id") == pkg_id or not pkg_id:
                        selected_package = pkg
                        break

            if selected_package:
                self.active_cart = build_cart(selected_package, self.raw_res["query"])
                self.booking_state = "awaiting_checkout_info"
                return {
                    "text": "Для оформления **демо-брони** укажите, пожалуйста, ваше имя, телефон и имена всех гостей.",
                    "buttons": []
                }
            return {"text": "Не удалось найти выбранный пакет для демо-брони.", "buttons": []}

        # --- Пункт 2: Запрос «куда поехать» ---
        if "куда поехать" in text_l or "предложи направления" in text_l:
            res_comp = compare_destinations(text, COVERAGE_CITIES, self.slots)
            self.raw_res = res_comp
            api_out = to_api_compare(res_comp)
            return {
                "text": api_out.get("fallback_text", "Вот доступные направления для отдыха:"),
                "buttons": api_out.get("buttons", [])
            }

        # --- Пункт 1 & 7: Извлечение слотов, адаптер, поиск через plan_trip ---
        raw_slots = extract_slots(user_text, self.slots.model_dump())
        if raw_slots:
            self.slots = TravelSlots.model_validate(raw_slots)

        query = slots_to_query(self.slots)

        # Вызов реальной функции поиска из app/
        self.raw_res = plan_trip(query)

        # Обработка нехватки данных (missing / errors)
        if self.raw_res.get("missing") or self.raw_res.get("errors"):
            missing_fields = ", ".join(self.raw_res.get("missing", []))
            err_msg = ", ".join(self.raw_res.get("errors", []))
            msg = "Пожалуйста, уточните следующие данные:"
            if missing_fields:
                msg += f"\n- Обязательные поля: {missing_fields}"
            if err_msg:
                msg += f"\n- Ошибки: {err_msg}"
            return {"text": msg, "buttons": []}

        # Обработка отсутствия результатов (no_results -> suggestions)
        if self.raw_res.get("no_results") and self.raw_res.get("suggestions"):
            sugg_text = "\n".join([f"• {s}" for s in self.raw_res["suggestions"]])
            return {
                "text": f"К сожалению, по вашему запросу ничего не найдено. Рекомендуем посмотреть:\n{sugg_text}",
                "buttons": []
            }

        # Генерация API ответа через output.py
        api_out = to_api(self.raw_res)

        # Очеловечивание через LLM
        human_text = reply_to_user(user_text, {"api_data": api_out, "history": self.chat_history[-5:]})
        self.chat_history.append({"role": "assistant", "content": human_text})

        # --- Пункт 6: Возврат словаря с text и buttons ---
        return {
            "text": human_text,
            "buttons": api_out.get("buttons", [])
        }

    # --- Пункт 6: Вызов через to_thread ---
    def handle(self, user_text: str) -> dict:
        return asyncio.run(asyncio.to_thread(self._handle_sync, user_text))

    def _handle_sync(self, user_text: str) -> dict:
        return asyncio.run(self.handle_async(user_text))
