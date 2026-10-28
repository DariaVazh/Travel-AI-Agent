import os
import asyncio
import logging
import random
import string
import re
from copy import deepcopy
from pathlib import Path
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, Router, html, BaseMiddleware
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, FSInputFile
)
from agent.agent import TravelAgent
from agent import storage
from agent.memory_service import checkpoint_memory
from database.user_repository import (
    get_or_create_user,
    get_user_profile,
    save_user_phone, get_user_memory
)
from database.booking_repository import (
    create_demo_booking,
    get_user_bookings, get_booking,
)
from time import monotonic
from contextlib import suppress

load_dotenv()
logging.basicConfig(level=logging.INFO)

router = Router()
user_agents = {}
_memory_locks: dict[int, asyncio.Lock] = {}
MEMORY_IDLE_SECONDS = 3 * 60
MEMORY_RETRY_SECONDS = 60

_last_activity: dict[int, float] = {}
_busy_users: dict[int, int] = {}
_memory_retry_after: dict[int, float] = {}


class ActivityMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if user is None:
            return await handler(event, data)

        user_id = user.id
        _last_activity[user_id] = monotonic()
        _busy_users[user_id] = _busy_users.get(user_id, 0) + 1

        try:
            return await handler(event, data)
        finally:
            _busy_users[user_id] -= 1
            # Отсчитываем тишину после завершения обработки.
            _last_activity[user_id] = monotonic()


class Flow(StatesGroup):
    waiting_contact = State()
    chatting = State()
    choosing_hotel = State()
    waiting_payment = State()
    waiting_confirm_data = State()
    waiting_name = State()
    waiting_phone = State()


def get_auth_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Отправить контакт", request_contact=True)]
        ],
        resize_keyboard=True, one_time_keyboard=True,
    )


def get_main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Найти поездку")],
            [KeyboardButton(text="Начать сначала"), KeyboardButton(text="Мои брони")]
        ],
        resize_keyboard=True, one_time_keyboard=False,
    )


def get_search_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Начать сначала")],
            [KeyboardButton(text="Мои брони")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def get_chat_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Забронировать"), KeyboardButton(text="Показать другие")],
            [KeyboardButton(text="Мои брони"), KeyboardButton(text="Начать сначала")]
        ],
        resize_keyboard=True, one_time_keyboard=False
    )


async def create_agent(telegram_id: int) -> TravelAgent:

    agent = TravelAgent(user_id=str(telegram_id))
    agent.long_term_memory = await get_user_memory(telegram_id)

    return agent


async def require_registration(message: Message, state: FSMContext) -> dict | None:
    user = await get_user_profile(message.from_user.id)
    if not user or not user.get("phone_number"):
        await message.answer(
            "Сначала зарегистрируйтесь: отправьте свой контакт.",
            reply_markup=get_auth_menu(),
        )
        await state.set_state(Flow.waiting_contact)
        return None
    return user


def clean_markdown(text: str) -> str:
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'^###\s*(.*)$', r'<b>\1</b>', text, flags=re.MULTILINE)
    text = re.sub(r'^---$', '', text, flags=re.MULTILINE)
    text = text.replace('*', '')
    return text


@router.message(CommandStart())
async def start(message: Message, state: FSMContext):

    tg_user = message.from_user

    await get_or_create_user(
        telegram_id=tg_user.id,
        name=tg_user.full_name
    )

    user = await get_user_profile(tg_user.id)

    registered = bool(user and user.get("phone_number"))
    if registered:
        display_name = user.get("full_name")
        caption = f"С возвращением, {display_name}!👋\n\nКуда хотите поехать?"
        keyboard = get_main_menu()
    else:
        caption = (
            "Привет! Скажи мне, куда хочешь отправиться — остальное устрою я ✈️\n"
            "Сначала зарегистрируемся — нажми кнопку ниже."
        )
        keyboard = get_auth_menu()

    picture = Path(__file__).with_name("two.png")
    if picture.is_file():
        try:
            await message.answer_photo(
                photo=FSInputFile(str(picture)),
                caption=caption,
                reply_markup=keyboard,
            )
        except Exception:
            logging.exception("Не удалось отправить стартовое изображение")
            await message.answer(caption, reply_markup=keyboard)
    else:
        await message.answer(caption, reply_markup=keyboard)

    if registered:
        if tg_user.id not in user_agents:
            user_agents[tg_user.id] = await create_agent(tg_user.id)
        await state.set_state(Flow.chatting)
    else:
        await state.set_state(Flow.waiting_contact)


@router.message(F.text == "Найти поездку")
async def find_trip(message: Message, state: FSMContext):
    if not await require_registration(message, state):
        return

    await message.answer(
        "Слушаю вас! Опишите поездку 👇",
        reply_markup=get_search_keyboard())
    await state.set_state(Flow.chatting)


@router.message(Flow.waiting_contact, F.contact)
async def on_contact(message: Message, state: FSMContext):
    telegram_id = message.from_user.id
    if message.contact.user_id != telegram_id:
        await message.answer(
            "Пожалуйста, отправьте свой номер кнопкой «Отправить контакт».",
            reply_markup=get_auth_menu(),
        )
        return

    await get_or_create_user(
        telegram_id=telegram_id,
        name=message.from_user.full_name,
    )
    await save_user_phone(telegram_id, message.contact.phone_number)

    if telegram_id not in user_agents:
        user_agents[telegram_id] = await create_agent(telegram_id)

    await message.answer(
        f"Спасибо, {message.from_user.full_name}!\n"
        "Теперь опишите свою идеальную поездку (куда, когда, с кем, бюджет).",
        reply_markup=get_main_menu(),
    )
    await state.set_state(Flow.chatting)



@router.message(F.text == "Мои брони")
async def show_bookings(message: Message, state: FSMContext):

    user = await require_registration(message, state)
    if user is None:
        return

    bookings = await get_user_bookings(user["id"])

    if not bookings:
        await message.answer(
            "У вас пока нет сохранённых броней.",
            reply_markup=get_main_menu()
        )
        return

    keyboard = []

    for booking in bookings:
        keyboard.append([
            InlineKeyboardButton(
                text=f"№{booking['id']} — {booking['hotel_name']}",
                callback_data=f"booking:{booking['id']}"
            )
        ])

    await message.answer(
        "📋 Ваши бронирования:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=keyboard
        )
    )


@router.callback_query(F.data.startswith("booking:"))
async def show_booking_details(callback: CallbackQuery):

    await callback.answer()

    user = await get_user_profile(callback.from_user.id)

    if user is None:
        await callback.message.answer("Пользователь не найден.")
        return

    booking_id = int(callback.data.split(":")[1])

    booking = await get_booking(
        user_id=user["id"],
        booking_id=booking_id
    )

    if booking is None:
        await callback.message.answer(
            "Бронирование не найдено."
        )
        return

    text = (
        f"🏨 Бронирование №{booking['id']}\n\n"
        f"Отель: {booking['hotel_name']}\n"
        f"Город: {booking['destination']}\n"
        f"Заезд: {booking['check_in']}\n"
        f"Выезд: {booking['check_out']}\n"
        f"Стоимость: {booking['total_price']} "
        f"{booking['currency']}\n"
        f"Статус: {booking['status']}"
    )

    await callback.message.answer(text)



@router.callback_query(F.data.startswith("pick:"))
async def process_pick(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    agent = user_agents.get(user_id)
    if not agent:
        await callback.message.answer("Пожалуйста, начните с команды /start")
        return

    package_id = callback.data.removeprefix("pick:")
    result = agent.raw_res or {}

    package = next(
        (
            item for item in result.get("packages", [])
            if item["id"] == package_id
        ),
        None,
    )
    query = result.get("query")

    if package is None or not isinstance(query, dict):
        await callback.message.answer(
            "Этот вариант больше недоступен. Повторите поиск."
        )
        return

    if not package.get("hotel") or not query.get("date_to"):
        await callback.message.answer(
            "Для бронирования проживания нужны отель и дата выезда."
        )
        return

    await state.update_data(
        selected_package=deepcopy(package),
        selected_query=deepcopy(query),
    )

    # text = callback.data
    # response = await agent.handle_async(text)
    # answer_text = response.get("text", "")
    #
    # answer_text = clean_markdown(answer_text)
    # await callback.message.answer(answer_text, parse_mode="HTML")

    await callback.message.answer(
        "Нажмите «Забронировать», чтобы продолжить.",
        reply_markup=get_chat_keyboard()
    )

    await state.set_state(Flow.choosing_hotel)


@router.message(Flow.choosing_hotel, F.text == "Забронировать")
async def start_booking(message: Message, state: FSMContext):
    if not await require_registration(message, state):
        return

    data = await state.get_data()

    if (
            data.get("selected_package") is None
            or data.get("selected_query") is None
    ):
        await message.answer("Сначала выберите вариант поездки.")
        return

    await state.update_data(hotel_name="Выбранный отель")

    telegram_id = message.from_user.id
    user = await get_user_profile(telegram_id)

    full_name = user.get("full_name")
    phone = user.get("phone_number")

    if full_name and phone:
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Всё верно")],
                [KeyboardButton(text="Изменить ФИО"), KeyboardButton(text="Изменить телефон")],
            ],
            resize_keyboard=True,
        )
        await message.answer(
            "Для оформления демо-брони я использую следующие данные:\n"
            f"👤 {html.quote(str(full_name))}\n"
            f"📱 {html.quote(str(phone))}\n\n"
            "Всё верно?",
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        await state.set_state(Flow.waiting_confirm_data)
    else:
        await message.answer("Введите ваше ФИО:", reply_markup=ReplyKeyboardRemove())
        await state.set_state(Flow.waiting_name)


@router.message(Flow.waiting_confirm_data, F.text == "Всё верно")
async def confirm_data(message: Message, state: FSMContext):
    await show_payment_button(message, state)


@router.message(Flow.waiting_confirm_data, F.text == "Изменить ФИО")
async def change_name(message: Message, state: FSMContext):
    await message.answer("Введите новое ФИО:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(Flow.waiting_name)


@router.message(Flow.waiting_confirm_data, F.text == "Изменить телефон")
async def change_phone(message: Message, state: FSMContext):
    await message.answer("Введите новый номер телефона", reply_markup=ReplyKeyboardRemove())
    await state.set_state(Flow.waiting_phone)


@router.message(Flow.waiting_name, F.text)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    user = await get_user_profile(message.from_user.id)
    if user and user.get("phone_number"):
        await show_payment_button(message, state)
    else:
        await message.answer("Теперь введите номер телефона (например: +7 999 123-45-67):")
        await state.set_state(Flow.waiting_phone)


@router.message(Flow.waiting_phone, F.text)
async def process_phone(message: Message, state: FSMContext):
    phone = message.text.strip()
    digits = re.sub(r"\D", "", phone)
    if not (7 <= len(digits) <= 15):
        await message.answer("Введите номер телефона с 7–15 цифрами.")
        return
    await state.update_data(phone=phone)
    await show_payment_button(message, state)


async def show_payment_button(message: Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Оплатить (Демо)")], [KeyboardButton(text="Отмена")]],
        resize_keyboard=True, one_time_keyboard=True
    )
    await message.answer(
        "Данные сохранены.\n\n"
        "⚠️ <b>Важно:</b> Мы не запрашиваем данные банковских карт в целях безопасности. "
        "Нажмите кнопку ниже, чтобы имитировать оплату.",
        reply_markup=kb,
        parse_mode="HTML"
    )
    await state.set_state(Flow.waiting_payment)


@router.message(Flow.waiting_payment, F.text == "Оплатить (Демо)")
async def process_payment(message: Message, state: FSMContext):
    data = await state.get_data()
    user = await get_user_profile(message.from_user.id)

    full_name = data.get("full_name") or (user or {}).get("full_name")
    phone = data.get("phone") or (user or {}).get("phone_number")


    from app.cart import build_cart, mock_checkout
    data = await state.get_data()
    user = await get_user_profile(message.from_user.id)

    package = data.get("selected_package")
    query = data.get("selected_query")

    if user is None or package is None or query is None:
        await message.answer("Сначала выберите вариант поездки.")
        return

    cart = build_cart(package, query)

    traveler = {
        "contact_name": full_name,
        "contact_phone": phone,
        "guest_names": [
            f"Гость {i + 1}"
            for i in range(query["guests"])
        ]
    }

    result = mock_checkout(cart, traveler)
    if result["status"] == "confirmed":
        # booking_id = result["booking_id"]
        total = result["total"]
        try:
            booking_id = await create_demo_booking(
                user_id=user["id"],
                query=query,
                package=package,
            )
        except Exception:
            logging.exception("Не удалось сохранить демо-бронь")
            await message.answer(
                "Не удалось сохранить бронь. Подтверждение не выдано."
            )
            return

        await state.clear()
        await state.set_state(Flow.chatting)

        await message.answer(
            f"✅ <b>Бронирование подтверждено!</b>\n\n"
            f"Номер вашей брони: <code>{html.quote(str(booking_id))}</code>\n"
            f"Итого: {html.quote(str(package['total_price']))} ₽\n"
            f"Гость: {html.quote(full_name)}\n\n"
            f"Ваучер отправлен на почту (демо). Спасибо, что выбрали нас!",
            reply_markup=get_main_menu(),
            parse_mode="HTML"
        )
    else:
        await message.answer(f"Ошибка при оплате: не хватает данных ({result.get('missing')})")


@router.message(Flow.waiting_payment, F.text == "Отмена")
async def cancel_payment(message: Message, state: FSMContext):
    await message.answer("Хорошо, отменили. Чем еще помочь?", reply_markup=get_main_menu())
    await state.set_state(Flow.chatting)


@router.message(F.text == "Показать другие")
async def process_more(message: Message, state: FSMContext):
    if not await require_registration(message, state):
        return
    await message.answer(
        "Напишите, что именно хотите изменить (например: найди варианты дешевле).",
        reply_markup=get_search_keyboard(),
    )
    await state.set_state(Flow.chatting)


@router.message(F.text == "Начать сначала")
async def process_restart(message: Message, state: FSMContext):
    if not await require_registration(message, state):
        return
    telegram_id = message.from_user.id
    old_agent = user_agents.get(telegram_id)

    if old_agent is not None:
        lock = _memory_locks.setdefault(telegram_id, asyncio.Lock())
        try:
            async with lock:
                await checkpoint_memory(old_agent, telegram_id)
        except Exception:
            logging.exception("Не удалось сохранить память перед новой сессией")
            await message.answer(
                "Не удалось сохранить предпочтения из текущей беседы. "
                "Попробуйте начать сначала ещё раз."
            )
            return

    user_agents[telegram_id] = await create_agent(telegram_id)
    await state.clear()
    await state.set_state(Flow.chatting)
    await message.answer(
        "Давайте начнём сначала! Куда хотите отправиться?",
        reply_markup=get_search_keyboard(),
    )


@router.message(Flow.chatting, F.text)
async def handle_chat(message: Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip()

    if user_id not in user_agents:
        user_agents[user_id] = await create_agent(user_id)

    agent = user_agents[user_id]
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    thinking_msg = await message.answer("🔍 Подбираю лучшие варианты...")

    try:
        response = await agent.handle_async(text)
        answer_text = response.get("text", "")
        buttons = response.get("buttons", [])

        if "Обязательные поля:" in answer_text or "Ошибки:" in answer_text:
            missing_fields = re.findall(
                r'(origin|destination|date_from|date_to|transport|adults|children|budget|pets|hotel_min_stars)',
                answer_text)

            if missing_fields:
                field = missing_fields[0]

                if field in ("origin", "destination"):
                    if field == "origin":
                        agent.slots.origin = text.capitalize()
                    else:
                        agent.slots.destination = text.capitalize()

                elif field in ("date_from", "date_to"):
                    date_match = re.search(r'(\d{4})[-./](\d{2})[-./](\d{2})', text)
                    if date_match:
                        formatted_date = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"
                        if field == "date_from":
                            agent.slots.dates.date_from = formatted_date
                        else:
                            agent.slots.dates.date_to = formatted_date
                    else:
                        await message.answer("Пожалуйста, введите дату в формате ГГГГ-ММ-ДД (например: 2027-06-10).")
                        await thinking_msg.delete()
                        return

                elif field == "transport":
                    if any(w in text.lower() for w in ["самолет", "plane", "лететь"]):
                        agent.slots.transport.modes = ["plane"]
                    elif any(w in text.lower() for w in ["поезд", "train", "ехать"]):
                        agent.slots.transport.modes = ["train"]
                    else:
                        agent.slots.transport.modes = ["any"]

                elif field == "adults":
                    num_match = re.search(r'\d+', text)
                    if num_match:
                        agent.slots.travelers.adults = int(num_match.group())

                elif field == "children":
                    num_match = re.search(r'\d+', text)
                    if num_match:
                        agent.slots.travelers.children = int(num_match.group())

                elif field == "budget":
                    num_match = re.search(r'\d+', text)
                    if num_match:
                        agent.slots.budget.amount = float(num_match.group())

                await thinking_msg.delete()
                await message.answer(f"Понял, вы указали: {text}. Продолжаю поиск...")
                response = await agent.handle_async(f"Я указал {text}, продолжай")
                answer_text = response.get("text", "")
                buttons = response.get("buttons", [])
                thinking_msg = await message.answer("🔍 Ищу дальше...")

        await thinking_msg.delete()

        answer_text = clean_markdown(answer_text)

        await message.answer(answer_text, parse_mode="HTML")

        if buttons:
            inline_kb = []
            for btn in buttons:
                inline_kb.append([InlineKeyboardButton(text=btn["label"], callback_data=btn["callback"])])
            await message.answer("Нажмите, чтобы выбрать вариант:",
                                 reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_kb))
            await state.set_state(Flow.choosing_hotel)
        elif "Забронировать" in answer_text or "бронь" in answer_text.lower():
            await state.set_state(Flow.waiting_payment)

    except Exception as e:
        logging.error(f"ОШИБКА: {e}")
        try:
            await thinking_msg.delete()
        except:
            pass
        await message.answer(f"Ошибка: {e}")


async def memory_autosave_loop():
    while True:
        await asyncio.sleep(60)

        for user_id, agent in list(user_agents.items()):
            last_activity = _last_activity.get(user_id)
            if last_activity is None:
                continue

            now = monotonic()

            if _busy_users.get(user_id, 0):
                continue

            if now - last_activity < MEMORY_IDLE_SECONDS:
                continue

            if now < _memory_retry_after.get(user_id, 0):
                continue

            if agent.memory_saved_upto >= len(agent.chat_history):
                continue

            lock = _memory_locks.setdefault(user_id, asyncio.Lock())

            if lock.locked():
                continue

            try:
                async with lock:
                    # Пока обходили пользователей, сессия могла смениться.
                    if user_agents.get(user_id) is not agent:
                        continue

                    if _busy_users.get(user_id, 0):
                        continue

                    if (
                        monotonic() - _last_activity[user_id]
                        < MEMORY_IDLE_SECONDS
                    ):
                        continue

                    await asyncio.wait_for(
                        checkpoint_memory(agent, user_id),
                        timeout=90,
                    )

                _memory_retry_after.pop(user_id, None)

            except Exception:
                logging.exception(
                    "Не удалось автоматически сохранить память: user_id=%s",
                    user_id,
                )
                _memory_retry_after[user_id] = (
                    monotonic() + MEMORY_RETRY_SECONDS
                )


async def main():
    bot = Bot(token=os.getenv("BOT_TOKEN"))
    dp = Dispatcher(storage=MemoryStorage())

    activity = ActivityMiddleware()
    router.message.outer_middleware(activity)
    router.callback_query.outer_middleware(activity)

    dp.include_router(router)

    memory_task = asyncio.create_task(memory_autosave_loop())

    try:
        print("Бот запущен.")
        await dp.start_polling(bot)
    finally:
        memory_task.cancel()
        with suppress(asyncio.CancelledError):
            await memory_task


if __name__ == "__main__":
    asyncio.run(main())