import os
import asyncio
import logging
import random
import string
import re
from pathlib import Path
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, Router, html
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

load_dotenv()
logging.basicConfig(level=logging.INFO)

router = Router()
user_agents = {}
_memory_locks: dict[int, asyncio.Lock] = {}


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
            [KeyboardButton(text="Отправить контакт", request_contact=True), KeyboardButton(text="Мои брони")]
        ],
        resize_keyboard=True, one_time_keyboard=False,
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
    await message.answer(
        "Слушаю вас! Опишите поездку 👇",
        reply_markup=ReplyKeyboardRemove())
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
    if not await require_registration(message, state):
        return

    routes = storage.list_routes(user_id=str(message.from_user.id))

    if not routes:
        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Найти поездку")]],
            resize_keyboard=True
        )
        await message.answer("У вас пока нет сохраненных броней. Хотите найти поездку?", reply_markup=kb)
        return

    text = "📋 <b>Ваши последние брони:</b>\n\n"
    for r in routes[-3:]:
        pkg = r.get("package") or {}
        b_id = pkg.get("booking_id", "Без номера")
        saved_at = r.get("saved_at", "")[:10]
        text += f"🔖 <code>{html.quote(b_id)}</code> (от {saved_at})\n"

    await message.answer(text, parse_mode="HTML", reply_markup=get_main_menu())


@router.callback_query(F.data.startswith("pick:"))
async def process_pick(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    agent = user_agents.get(user_id)
    if not agent:
        await callback.message.answer("Пожалуйста, начните с команды /start")
        return

    text = callback.data
    response = await agent.handle_async(text)
    answer_text = response.get("text", "")

    answer_text = clean_markdown(answer_text)

    await callback.message.answer(answer_text, parse_mode="HTML")
    await state.set_state(Flow.waiting_payment)


@router.message(Flow.choosing_hotel, F.text == "Забронировать")
async def start_booking(message: Message, state: FSMContext):
    if not await require_registration(message, state):
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

    try:
        from app.cart import build_cart, mock_checkout
        fake_package = {
            "id": "pkg_demo_123",
            "total_price": 65000,
            "outbound": {"carrier": "SU-1234", "origin": "Москва", "destination": "Сочи", "depart": "2027-06-10T10:00",
                         "arrive": "2027-06-10T12:00", "price": 15000},
            "return": None,
            "hotel": {"name": data.get("hotel_name", "Тестовый отель"), "nights": 7, "total_price": 35000},
            "transfer": None
        }
        fake_query = {"guests": 2}

        cart = build_cart(fake_package, fake_query)
        traveler = {
            "contact_name": full_name,
            "contact_phone": phone,
            "guest_names": ["Гость 1", "Гость 2"]
        }

        result = mock_checkout(cart, traveler)
        if result["status"] == "confirmed":
            booking_id = result["booking_id"]
            total = result["total"]
            storage.save_route(
                slots={"name": full_name, "phone": phone},
                hotels=[],
                chosen={"hotel": data.get("hotel_name"), "status": "booked"},
                note="Оплачено (демо)",
                user_id=str(message.from_user.id),
                package={"booking_id": booking_id},
                route_id=booking_id
            )
            await message.answer(
                f"✅ <b>Бронирование подтверждено!</b>\n\n"
                f"Номер вашей брони: <code>{html.quote(booking_id)}</code>\n"
                f"Итого: {html.quote(str(total))} ₽\n"
                f"Гость: {html.quote(full_name)}\n\n"
                f"Ваучер отправлен на почту (демо). Спасибо, что выбрали нас!",
                reply_markup=ReplyKeyboardRemove(),
                parse_mode="HTML"
            )
        else:
            await message.answer(f"Ошибка при оплате: не хватает данных ({result.get('missing')})")

    except Exception as e:
        logging.error(f"Ошибка при имитации оплаты: {e}")
        booking_id = "MOCK-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        await message.answer(
            f"✅ <b>Бронь оформлена (упрощенная демо)!</b>\n\n"
            f"Номер: <code>{html.quote(booking_id)}</code>\n"
            f"Гость: {html.quote(full_name)}",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="HTML"
        )
    await state.clear()


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
        reply_markup=ReplyKeyboardRemove(),
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
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(Flow.chatting, F.text)
async def handle_chat(message: Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip()

    if user_id not in user_agents:
        user_agents[user_id] = TravelAgent(user_id=str(user_id))

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


async def main():
    bot = Bot(token=os.getenv("BOT_TOKEN"))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    print("Бот запущен.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())