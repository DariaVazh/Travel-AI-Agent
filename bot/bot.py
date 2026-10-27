import os
import asyncio
import logging
import random
import string
import re
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)

from agent.agent import TravelAgent
import database
from agent import storage

load_dotenv()
logging.basicConfig(level=logging.INFO)

router = Router()
user_agents = {}

class Flow(StatesGroup):
    waiting_contact = State()
    chatting = State()
    choosing_hotel = State()
    waiting_payment = State()

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
    # Проверяем, зарегистрирован ли пользователь (по базе)
    user = database.get_user(message.from_user.id)
    
    if user:
        # Если уже зарегистрирован, сразу в чат
        await message.answer(
            f"С возвращением, {user['full_name']}!\n"
            "Опиши свою идеальную поездку (куда, когда, с кем, бюджет).",
            reply_markup=get_main_menu(),
        )
        await state.set_state(Flow.chatting)
        if message.from_user.id not in user_agents:
            user_agents[message.from_user.id] = TravelAgent(user_id=str(message.from_user.id))
    else:
        # Если новый — просим контакт
        await message.answer(
            "Привет! Скажа куда хочешь отправиться - остальное устроит агент ✈️\n"
            "Сначала зарегистрируемся — нажми кнопку ниже.",
            reply_markup=get_main_menu(),
        )
        await state.set_state(Flow.waiting_contact)

# КНОПКА "НАЙТИ ПОЕЗДКУ"
@router.message(F.text == "Найти поездку")
async def find_trip(message: Message, state: FSMContext):
    await message.answer("Отлично! Куда хотите поехать? Опишите свою идеальную поездку.", reply_markup=ReplyKeyboardRemove())
    await state.set_state(Flow.chatting)

#РЕГИСТРАЦИЯ
@router.message(Flow.waiting_contact, F.contact)
async def on_contact(message: Message, state: FSMContext):
    database.save_user(message.from_user.id, message.from_user.full_name, message.contact.phone_number)
    user_agents[message.from_user.id] = TravelAgent(user_id=str(message.from_user.id))
    
    await message.answer(
        f"Спасибо, {message.from_user.full_name}!\n"
        "Теперь опиши свою идеальную поездку (куда, когда, с кем, бюджет).",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(Flow.chatting)

#МОИ БРОНИ
@router.message(F.text == "Мои брони")
async def show_bookings(message: Message):
    user_id = str(message.from_user.id)
    routes = storage.list_routes(user_id=user_id)
    
    if not routes:
        # Если броней нет, предлагаем начать поиск
        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Найти поездку")]],
            resize_keyboard=True
        )
        await message.answer("У вас пока нет сохраненных броней. Хотите найти поездку?", reply_markup=kb)
        return
    
    text = "📋 **Ваши последние брони:**\n\n"
    for r in routes[-3:]:
        pkg = r.get("package") or {}
        b_id = pkg.get("booking_id", "Без номера")
        saved_at = r.get("saved_at", "")[:10]
        text += f"🔖 `{b_id}` (от {saved_at})\n"
    
    await message.answer(text, parse_mode="Markdown", reply_markup=get_main_menu())

# ДИАЛОГ
@router.message(Flow.chatting, F.text)
async def handle_chat(message: Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip()
    
    if user_id not in user_agents:
        user_agents[user_id] = TravelAgent(user_id=str(user_id))
        
    agent = user_agents[user_id]
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    
    try:
        # асинхронный метод Даши
        response = await agent.handle_async(text)
        
        answer_text = response.get("text", "")
        buttons = response.get("buttons", [])
        
        # Отправляем текст
        await message.answer(answer_text)
        
        if buttons:
            inline_kb = []
            for btn in buttons:
                inline_kb.append([InlineKeyboardButton(text=btn["label"], callback_data=btn["callback"])])
            
            await message.answer("Нажмите, чтобы выбрать вариант:", reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_kb))
            await state.set_state(Flow.choosing_hotel)
        elif "Забронировать" in answer_text or "бронь" in answer_text.lower():
            await state.set_state(Flow.waiting_payment)
            
    except Exception as e:
        logging.error(f"ОШИБКА: {e}")
        await message.answer(f"Ошибка: {e}")

# ОБРАБОТЧИК КНОПОК ВЫБОРА
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
    
    await callback.message.answer(answer_text)
    await state.set_state(Flow.waiting_payment)

#ОБРАБОТКА ТЕКСТА ДЛЯ БРОНИРОВАНИЯ
@router.message(Flow.waiting_payment, F.text)
async def process_booking_info(message: Message, state: FSMContext):
    user_id = message.from_user.id
    agent = user_agents.get(user_id)
    
    if message.text == "Отмена":
        await message.answer("Хорошо, отменили. Чем еще помочь?", reply_markup=get_main_menu())
        await state.set_state(Flow.chatting)
        return

    response = await agent.handle_async(message.text)
    answer_text = response.get("text", "")
    
    await message.answer(answer_text)
    
    if "бронь" in answer_text.lower() or "✅" in answer_text:
        await message.answer("Вы можете продолжить поиск или посмотреть брони.", reply_markup=get_chat_keyboard())
        await state.set_state(Flow.chatting)

# ОСТАЛЬНЫЕ КНОПКИ 
@router.message(F.text == "Показать другие")
async def process_more(message: Message, state: FSMContext):
    await message.answer("Напишите, что именно хотите изменить (например: 'дешевле').", 
                         reply_markup=ReplyKeyboardRemove())
    await state.set_state(Flow.chatting)

@router.message(F.text == "Начать сначала")
async def process_restart(message: Message, state: FSMContext):
    user_agents[message.from_user.id] = TravelAgent(user_id=str(message.from_user.id))
    await message.answer("Давайте начнем сначала! Куда хотите поехать?", 
                         reply_markup=ReplyKeyboardRemove())
    await state.set_state(Flow.chatting)

async def main():
    database.init_db()
    bot = Bot(token=os.getenv("BOT_TOKEN"))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    print("Бот запущен (с меню 'Найти поездку').")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())