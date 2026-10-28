import os
import asyncio
import logging
import random
import string
import re
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
from botD import database
from agent import storage
from app.weather import get_weather, weather_text

load_dotenv()
logging.basicConfig(level=logging.INFO)

router = Router()
user_agents = {}


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


@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    user = database.get_user(message.from_user.id)

    try:
        photo = FSInputFile("two.png")
        if user:
            caption = f"С возвращением, {user['full_name']}!👋\n\nКуда хотите поехать?"
            kb = get_main_menu()
        else:
            caption = "Привет! Скажи мне куда хочешь отправиться - остальное устрою я✈️\nСначала зарегистрируемся — нажми кнопку ниже."
            kb = get_auth_menu()

        await message.answer_photo(photo=photo, caption=caption, reply_markup=kb)
    except Exception as e:
        logging.error(f"Не удалось отправить картинку: {e}")
        if user:
            caption = f"С возвращением, {user['full_name']}!👋\n\nКуда хотите поехать?"
            kb = get_main_menu()
        else:
            caption = "Привет! Скажи мне куда хочешь отправиться - остальное устрою я✈️\nСначала зарегистрируемся — нажми кнопку ниже."
            kb = get_auth_menu()
        await message.answer(caption, reply_markup=kb)

    if user:
        await state.set_state(Flow.chatting)
        if message.from_user.id not in user_agents:
            user_agents[message.from_user.id] = TravelAgent(user_id=str(message.from_user.id))
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
    database.save_user(message.from_user.id, message.from_user.full_name, message.contact.phone_number)
    user_agents[message.from_user.id] = TravelAgent(user_id=str(message.from_user.id))

    await message.answer(
        f"Спасибо, {message.from_user.full_name}!\n"
        "Теперь опиши свою идеальную поездку (куда, когда, с кем, бюджет).",
        reply_markup=get_main_menu(),
    )
    await state.set_state(Flow.chatting)


@router.message(F.text == "Мои брони")
async def show_bookings(message: Message):
    user_id = str(message.from_user.id)
    routes = storage.list_routes(user_id=user_id)

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

        answer_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', answer_text)

        await message.answer(answer_text, parse_mode="HTML")

        found_city = agent.slots.destination
        if found_city:
            try:
                from datetime import date, timedelta
                tomorrow = (date.today() + timedelta(days=1)).isoformat()

                date_from = agent.slots.dates.date_from or tomorrow
                date_to = agent.slots.dates.date_to or date_from

                weather = get_weather(found_city, date_from, date_to)
                if weather:
                    w_text = weather_text(found_city, weather)
                    await message.answer(w_text)
            except Exception as e:
                logging.error(f"Ошибка при получении погоды для {found_city}: {e}")

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

    answer_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', answer_text)

    await callback.message.answer(answer_text, parse_mode="HTML")
    await state.set_state(Flow.waiting_payment)


@router.message(Flow.choosing_hotel, F.text == "Забронировать")
async def start_booking(message: Message, state: FSMContext):
    user = database.get_user(message.from_user.id)
    await state.update_data(hotel_name="Выбранный отель")

    if user and user.get("full_name"):
        kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Всё верно")],
                [KeyboardButton(text="Изменить ФИО"), KeyboardButton(text="Изменить телефон")]
            ],
            resize_keyboard=True
        )
        await message.answer(
            f"Для оформления брони я использую данные из вашего профиля:\n"
            f"👤 {user['full_name']}\n"
            f"📱 {user['phone']}\n\n"
            f"Всё верно?",
            reply_markup=kb
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
    user = database.get_user(message.from_user.id)
    if user and user.get("phone"):
        await show_payment_button(message, state)
    else:
        await message.answer("Теперь введите номер телефона (например: +7 999 123-45-67):")
        await state.set_state(Flow.waiting_phone)


@router.message(Flow.waiting_phone, F.text)
async def process_phone(message: Message, state: FSMContext):
    await state.update_data(phone=message.text)
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
    user = database.get_user(message.from_user.id)

    full_name = data.get("full_name") or (user["full_name"] if user else "Гость")
    phone = data.get("phone") or (user["phone"] if user else "+79990000000")

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
    await message.answer("Напишите, что именно хотите изменить (например: найди варианты дешевле).",
                         reply_markup=ReplyKeyboardRemove())
    await state.set_state(Flow.chatting)


@router.message(F.text == "Начать сначала")
async def process_restart(message: Message, state: FSMContext):
    user_agents[message.from_user.id] = TravelAgent(user_id=str(message.from_user.id))
    await message.answer("Давайте начнем сначала! Куда хотите отправиться?",
                         reply_markup=ReplyKeyboardRemove())
    await state.set_state(Flow.chatting)


async def main():
    database.init_db()
    bot = Bot(token=os.getenv("BOT_TOKEN"))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    print("Бот запущен.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())