import asyncio
import uuid
from .slots_schema import TravelSlots, UserProfile
from .llm import extract_slots, reply_to_user
from .llm_config import slots_to_query
from .storage import save_route, list_routes

from app.search import plan_trip, replan, compare_destinations
from app.cart import build_cart, mock_checkout
from app.output import to_api

from datetime import date
today = date.today()

COVERAGE_CITIES = ["Сочи", "Москва", "Санкт-Петербург", "Казань", "Калининград"]

# Словарь: техническое поле -> (человеческая фраза, уточняющий вопрос)
FIELD_HUMAN = {
    "origin": ("город отправления", "Откуда вы планируете выезжать?"),
    "destination": ("направление", "Куда хотите поехать? Или подсказать варианты?"),
    "destination_flexible": ("гибкость по направлению", "Готовы рассмотреть любые направления?"),
    "dates": ("даты поездки", "Когда планируете поездку? Хотя бы месяц."),
    "date_from": ("дата начала", "Когда планируете выезжать?"),
    "date_to": ("дата окончания", "Насколько дней едете?"),
    "dates.date_from": ("дата начала", "Когда планируете выезжать?"),
    "dates.date_to": ("дата окончания", "Насколько дней едете?"),
    "dates.month": ("месяц поездки", "В каком месяце хотите поехать?"),
    "budget": ("бюджет", "Какой бюджет закладываете на поездку?"),
    "budget.amount": ("сумма бюджета", "Какой бюджет закладываете на поездку?"),
    "travelers": ("путешественники", "Сколько человек едет и с кем?"),
    "travelers.adults": ("взрослые", "Сколько взрослых едет?"),
    "travelers.children": ("дети", "Сколько детей едет? Укажите возраст, если есть."),
    "transport": ("транспорт", "Как предпочитаете добираться — самолёт, поезд или без разницы?"),
    "transport.modes": ("вид транспорта", "Как предпочитаете добираться — самолёт, поезд или без разницы?"),
    "preferences": ("предпочтения", "Что важно в поездке — море, тепло, звёзды отеля?"),
    "preferences.hotel_stars_min": ("звёздность отеля", "Какой минимальный уровень отеля рассматриваете?"),
}


class TravelAgent:
    def __init__(self, user_id: str = "default"):
        self.slots = TravelSlots()
        self.user_id = user_id
        self.session_id = f"rt_{uuid.uuid4().hex[:10]}"
        self.chat_history = []
        self.user_profile = UserProfile(user_id=user_id).model_dump()

        self.raw_res = None
        self.active_cart = None
        self.booking_state = None  # None | "awaiting_checkout_info"

    def feed_external_routes(self, data: dict):
        """Принимает JSON с готовыми маршрутами от внешней программы."""
        self.raw_res = data

    def get_user_profile_json(self) -> dict:
        return self.user_profile

    async def handle_async(self, user_text: str) -> dict:
        text = user_text.strip()
        text_l = text.lower()
        self.chat_history.append({"role": "user", "content": text})

        # --- Логика демо-бронирования ---
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
                query_data = self.raw_res.get("query")
                if not isinstance(query_data, dict):
                    query_data = slots_to_query(self.slots)
                self.active_cart = build_cart(selected_package, query_data)
                self.booking_state = "awaiting_checkout_info"
                return {
                    "text": "Для оформления **демо-брони** укажите, пожалуйста, ваше имя, телефон и имена всех гостей.",
                    "buttons": []
                }
            return {"text": "Не удалось найти выбранный пакет для демо-брони.", "buttons": []}

        # --- Запрос «куда поехать» / «предложи направления» ---
        # --- Запрос «куда поехать» / «предложи направления» ---
        # --- Запрос «куда поехать» / «предложи направления» ---
        if (
                "куда поехать" in text_l
                or "предложи направления" in text_l
                or "предложи варианты" in text_l
                or "какие направления" in text_l
                or "подскажи варианты" in text_l
        ):
            # Пользователь хочет предложения → destination должен быть пустым
            self.slots.destination = None
            self.slots.destination_flexible = True

            query = slots_to_query(self.slots)
            query["destination"] = None  # обязательно

            # Правильный вызов: только query и список городов
            res_comp = compare_destinations(query, COVERAGE_CITIES)
            self.raw_res = res_comp

            # Если функция вернула need_info / errors
            if res_comp.get("missing") or res_comp.get("errors") or res_comp.get("status") == "need_info":
                raw_missing = res_comp.get("missing", [])
                raw_errors = res_comp.get("errors", [])

                human_hints = []
                questions = []
                seen = set()
                for field in raw_missing:
                    if field in seen:
                        continue
                    seen.add(field)
                    human, question = FIELD_HUMAN.get(field, (field.replace("_", " "), None))
                    human_hints.append(human)
                    if question:
                        questions.append(question)

                if human_hints:
                    header = (f"Почти всё готово! Подскажите ещё {human_hints[0]} 🙏"
                              if len(human_hints) == 1
                              else "Чтобы предложить направления, мне нужно чуть больше информации:")
                else:
                    header = "Мне нужно чуть больше информации, чтобы предложить варианты."

                bullets = "\n".join(f"• {q}" for q in questions) if questions else "\n".join(
                    f"• {h}" for h in human_hints)
                msg = f"{header}\n{bullets}"

                if raw_errors:
                    msg += "\n\nЗаметил небольшую загвоздку:\n" + "\n".join(f"• {e}" for e in raw_errors)

                return {"text": msg, "buttons": []}

            # Успешный ответ
            api_out = to_api(res_comp) if "to_api" in globals() else res_comp
            text = api_out.get("text") or res_comp.get("text") or "Вот доступные направления для отдыха:"
            return {
                "text": text,
                "buttons": api_out.get("buttons", [])
            }

        # --- Извлечение слотов, адаптер, поиск через plan_trip ---
        raw_slots = extract_slots(user_text, self.slots.model_dump())
        print("\n=== DEBUG extract_slots ===")
        print("raw_slots:", raw_slots)
        print("===========================\n")

        if raw_slots:
            self.slots = TravelSlots.model_validate(raw_slots)
            if self.slots.dates.month and not self.slots.dates.date_from:
                try:
                    month = int(self.slots.dates.month)
                    year = today.year
                    # если месяц уже прошёл — берём следующий год
                    if month < today.month or (month == today.month and today.day > 28):
                        year += 1
                    self.slots.dates.date_from = f"{year}-{month:02d}-01"
                except Exception:
                    pass

        print("=== DEBUG current slots ===")
        print(self.slots.model_dump())
        print("===========================\n")

        query = slots_to_query(self.slots)

        # Вызов функции поиска из app/
        self.raw_res = plan_trip(query)

        # Обработка нехватки данных (missing / errors)
        if self.raw_res.get("missing") or self.raw_res.get("errors"):
            raw_missing = self.raw_res.get("missing", [])
            raw_errors = self.raw_res.get("errors", [])

            # 1) Собираем человеческие фразы и вопросы
            human_hints = []
            questions = []
            seen = set()
            for field in raw_missing:
                if field in seen:
                    continue
                seen.add(field)
                human, question = FIELD_HUMAN.get(
                    field,
                    (field.replace("_", " "), None),
                )
                human_hints.append(human)
                if question:
                    questions.append(question)

            # 2) Формируем дружелюбное сообщение
            if human_hints:
                if len(human_hints) == 1:
                    header = f"Почти всё готово! Подскажите ещё {human_hints[0]} 🙏"
                else:
                    header = "Чтобы подобрать маршрут, мне не хватает пары деталей:"
            else:
                header = "Мне нужно чуть больше информации, чтобы подобрать вариант."

            # 3) Если есть «человеческие» вопросы — задаём их, иначе показываем фразы списком
            if questions:
                bullets = "\n".join(f"• {q}" for q in questions)
            else:
                bullets = "\n".join(f"• {h}" for h in human_hints)

            msg = f"{header}\n{bullets}"

            # 4) Ошибки (валидация) — мягко, отдельным блоком
            if raw_errors:
                msg += "\n\nЗаметил небольшую загвоздку:"
                msg += "\n" + "\n".join(f"• {e}" for e in raw_errors)

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

        return {
            "text": human_text,
            "buttons": api_out.get("buttons", [])
        }

    def handle(self, user_text: str) -> dict:
        """Синхронная обёртка. Без вложенных asyncio.run."""
        return asyncio.run(self.handle_async(user_text))