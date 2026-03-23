import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

import config
from database import db
from keyboards import *
from utils.constants import *
from utils.helpers import *
from models import Rarity

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token=config.BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Состояния для FSM
class AdminStates(StatesGroup):
    waiting_for_card_name = State()
    waiting_for_card_rarity = State()
    waiting_for_card_image = State()
    waiting_for_card_description = State()
    waiting_for_card_video = State()
    waiting_for_user_id_premium = State()

# Словарь для хранения времени последнего поиска
user_last_find = {}

# === Middleware для проверки премиума ===
@dp.message.middleware()
async def check_premium_middleware(handler, event: Message, data: dict):
    if event.from_user:
        await db.check_premium_expired(event.from_user.id)
    return await handler(event, data)

# === Обработчики команд ===

@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username
    
    # Создаем или получаем пользователя
    user = await db.get_user(user_id)
    if not user:
        user = await db.create_user(user_id, username)
    
    await message.answer(
        WELCOME_TEXT,
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(user.is_premium if user else False)
    )

@dp.message(Command("profile"))
@dp.message(F.text == "👤 Профиль")
async def show_profile(message: Message):
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        user = await db.create_user(user_id, message.from_user.username)
    
    unique_cards = await db.get_user_cards_count(user_id)
    total_cards = await db.get_total_cards_count()
    
    progress = int((user.exp / user.next_level_exp) * 100)
    
    premium_status = "✅ Активен" if user.is_premium else "❌ Неактивен"
    if user.is_premium and user.premium_until:
        days_left = (user.premium_until - datetime.now()).days
        premium_status += f" (осталось {days_left} дн.)"
    
    profile_text = PROFILE_TEXT.format(
        user_id=user.id,
        username=message.from_user.full_name or user.username or "Не указано",
        level=user.level,
        level_emoji=get_level_emoji(user.level),
        exp=user.exp,
        next_exp=user.next_level_exp,
        progress=progress,
        cards_count=user.cards_count,
        total_finds=user.total_finds,
        unique_cards=unique_cards,
        total_cards=total_cards,
        premium_status=premium_status,
        created_date=user.created_at.strftime("%d.%m.%Y")
    )
    
    await message.answer(profile_text, parse_mode="Markdown")

@dp.message(Command("mellstroy"))
@dp.message(F.text == "🎴 Найти карточку")
async def find_card(message: Message):
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        user = await db.create_user(user_id, message.from_user.username)
    
    # Проверка кулдауна
    last_find = user_last_find.get(user_id, datetime.min)
    seconds_passed = (datetime.now() - last_find).total_seconds()
    
    if seconds_passed < config.CARD_FIND_COOLDOWN:
        wait_time = int(config.CARD_FIND_COOLDOWN - seconds_passed)
        await message.answer(
            f"⏳ Подожди {wait_time} секунд перед следующим поиском!",
            reply_markup=get_main_keyboard(user.is_premium)
        )
        return
    
    # Получаем случайную карточку
    card = await db.get_random_card(user.is_premium)
    
    if not card:
        await message.answer("😢 Ошибка! Попробуй позже.")
        return
    
    # Добавляем карточку пользователю
    count = await db.add_card_to_user(user_id, card.id)
    
    # Обновляем опыт и статистику
    exp_gain = {
        Rarity.COMMON: 10,
        Rarity.RARE: 20,
        Rarity.EPIC: 50,
        Rarity.LEGENDARY: 100
    }.get(card.rarity, 10)
    
    new_level, level_up = await db.update_user_exp(user_id, exp_gain)
    await db.update_stats(user_id, True)
    
    # Обновляем время последнего поиска
    user_last_find[user_id] = datetime.now()
    
    # Формируем ответ
    rarity_emoji = card.rarity.emoji
    rarity_text = {
        Rarity.COMMON: "Обычная",
        Rarity.RARE: "Редкая",
        Rarity.EPIC: "Эпическая",
        Rarity.LEGENDARY: "ЛЕГЕНДАРНАЯ!"
    }.get(card.rarity, "Обычная")
    
    caption = (
        f"{rarity_emoji} *Ты нашёл карточку:* {card.name}\n\n"
        f"⭐ *Редкость:* {rarity_text}\n"
        f"📖 *Описание:* {card.description}\n\n"
        f"📊 *У тебя теперь:* {count} шт.\n"
        f"✨ *Получено опыта:* +{exp_gain}\n"
    )
    
    if level_up:
        caption += f"\n🎉 *УРОВЕНЬ ПОВЫШЕН!* Теперь ты {new_level} уровень! 🎉"
    
    # Отправляем карточку
    if card.video_url:
        await message.answer_video(
            card.video_url,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(user.is_premium)
        )
    else:
        await message.answer_photo(
            card.image_url,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(user.is_premium)
        )

@dp.message(Command("collection"))
@dp.message(F.text == "📚 Моя коллекция")
async def show_collection(message: Message, page: int = 0):
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        user = await db.create_user(user_id, message.from_user.username)
    
    cards_per_page = 10
    cards = await db.get_user_cards(user_id, limit=cards_per_page, offset=page * cards_per_page)
    total_unique = await db.get_user_cards_count(user_id)
    
    if not cards:
        await message.answer(
            "📭 У тебя пока нет карточек! Используй /mellstroy чтобы найти первую карточку!",
            reply_markup=get_main_keyboard(user.is_premium)
        )
        return
    
    total_pages = (total_unique + cards_per_page - 1) // cards_per_page
    
    # Формируем текст коллекции
    text = f"📚 *Твоя коллекция* (Страница {page + 1}/{total_pages})\n\n"
    
    for card in cards:
        rarity_emoji = card.rarity.emoji
        text += f"{rarity_emoji} *{card.name}* — {card.count} шт.\n"
    
    text += f"\n📊 *Всего уникальных:* {total_unique}/{await db.get_total_cards_count()}"
    
    has_prev = page > 0
    has_next = page < total_pages - 1
    
    await message.answer(
        text,
        parse_mode="Markdown",
        reply_markup=get_collection_keyboard(page, total_pages, has_prev, has_next)
    )

@dp.callback_query(F.data.startswith("collection_page_"))
async def collection_page_callback(callback: CallbackQuery):
    page = int(callback.data.split("_")[-1])
    await show_collection(callback.message, page)
    await callback.answer()

@dp.callback_query(F.data == "refresh_collection")
async def refresh_collection(callback: CallbackQuery):
    await show_collection(callback.message, 0)
    await callback.answer("🔄 Коллекция обновлена")

@dp.message(Command("top"))
@dp.message(F.text == "🏆 Топ игроков")
async def show_top(message: Message):
    top_users = await db.get_top_users(10)
    
    if not top_users:
        await message.answer("Пока нет игроков в топе!")
        return
    
    text = "🏆 *Топ 10 коллекционеров* 🏆\n\n"
    
    for i, user in enumerate(top_users, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        username = user['username'] or f"ID:{user['id']}"
        text += f"{medal} {username} — {user['cards_count']} 🃏 (Ур. {user['level']})\n"
    
    await message.answer(text, parse_mode="Markdown")

@dp.message(Command("bonus"))
@dp.message(F.text == "⭐ Ежедневный бонус")
async def daily_bonus(message: Message):
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        user = await db.create_user(user_id, message.from_user.username)
    
    if await db.can_claim_daily_bonus(user_id):
        bonus_amount = config.DAILY_BONUS_AMOUNT
        if user.is_premium:
            bonus_amount = int(bonus_amount * 1.5)  # 50% бонус для премиум
        
        await db.claim_daily_bonus(user_id, bonus_amount)
        await message.answer(
            BONUS_TEXT.format(bonus=bonus_amount),
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            "❌ Ты уже получал бонус сегодня! Возвращайся завтра!",
            reply_markup=get_main_keyboard(user.is_premium)
        )

@dp.message(Command("premium"))
@dp.message(F.text == "💎 Купить премиум")
async def show_premium(message: Message):
    await message.answer(
        PREMIUM_TEXT,
        parse_mode="Markdown",
        reply_markup=get_premium_keyboard()
    )

@dp.callback_query(F.data.startswith("premium_"))
async def premium_callback(callback: CallbackQuery):
    days = int(callback.data.split("_")[1])
    
    prices = {
        7: 50,
        30: 150,
        90: 400
    }
    
    price = prices.get(days, 50)
    
    await callback.message.edit_text(
        f"💎 *Подтверждение покупки*\n\n"
        f"Премиум на {days} дней\n"
        f"Стоимость: {price}⭐\n\n"
        f"Подтверждаешь покупку?",
        parse_mode="Markdown",
        reply_markup=get_confirm_premium_keyboard(days, price)
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("confirm_premium_"))
async def confirm_premium(callback: CallbackQuery):
    _, days_str, price_str = callback.data.split("_")
    days = int(days_str)
    price = int(price_str)
    
    user_id = callback.from_user.id
    
    # Здесь должна быть интеграция с Telegram Stars
    # Пока просто выдаем премиум (для тестирования)
    await db.set_premium(user_id, days)
    
    await callback.message.edit_text(
        f"✅ *Премиум активирован!*\n\n"
        f"Теперь у тебя есть премиум на {days} дней!\n"
        f"Повышенный шанс легендарных карточек активирован! 🎉",
        parse_mode="Markdown"
    )
    
    await callback.message.answer(
        "Возвращайся в главное меню!",
        reply_markup=get_main_keyboard(True)
    )
    await callback.answer()

@dp.callback_query(F.data == "premium_cancel")
async def cancel_premium(callback: CallbackQuery):
    await callback.message.edit_text(
        "❌ Покупка отменена",
        reply_markup=get_premium_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "main_menu")
async def back_to_main_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    
    await callback.message.delete()
    await callback.message.answer(
        "Главное меню:",
        reply_markup=get_main_keyboard(user.is_premium if user else False)
    )
    await callback.answer()

# === Админ команды ===
@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id not in config.ADMIN_IDS:
        await message.answer("⛔ У вас нет доступа к этой команде!")
        return
    
    await message.answer(
        "👑 *Админ панель*\n\nВыберите действие:",
        parse_mode="Markdown",
        reply_markup=get_admin_keyboard()
    )

@dp.callback_query(F.data == "admin_add_card")
async def admin_add_card_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("⛔ Нет доступа")
        return
    
    await callback.message.answer("Введите название карточки:")
    await state.set_state(AdminStates.waiting_for_card_name)
    await callback.answer()

@dp.message(AdminStates.waiting_for_card_name)
async def admin_add_card_name(message: Message, state: FSMContext):
    await state.update_data(card_name=message.text)
    await message.answer(
        "Выберите редкость карточки:\n"
        "1 - Обычная\n"
        "2 - Редкая\n"
        "3 - Эпическая\n"
        "4 - Легендарная"
    )
    await state.set_state(AdminStates.waiting_for_card_rarity)

@dp.message(AdminStates.waiting_for_card_rarity)
async def admin_add_card_rarity(message: Message, state: FSMContext):
    rarity_map = {
        "1": Rarity.COMMON,
        "2": Rarity.RARE,
        "3": Rarity.EPIC,
        "4": Rarity.LEGENDARY
    }
    
    if message.text not in rarity_map:
        await message.answer("Пожалуйста, выберите цифру от 1 до 4")
        return
    
    await state.update_data(card_rarity=rarity_map[message.text])
    await message.answer("Введите URL изображения карточки:")
    await state.set_state(AdminStates.waiting_for_card_image)

@dp.message(AdminStates.waiting_for_card_image)
async def admin_add_card_image(message: Message, state: FSMContext):
    await state.update_data(card_image=message.text)
    await message.answer("Введите описание карточки:")
    await state.set_state(AdminStates.waiting_for_card_description)

@dp.message(AdminStates.waiting_for_card_description)
async def admin_add_card_description(message: Message, state: FSMContext):
    await state.update_data(card_description=message.text)
    await message.answer(
        "Введите URL видео (если есть) или отправьте 'нет':"
    )
    await state.set_state(AdminStates.waiting_for_card_video)

@dp.message(AdminStates.waiting_for_card_video)
async def admin_add_card_video(message: Message, state: FSMContext):
    video_url = None if message.text.lower() == "нет" else message.text
    
    data = await state.get_data()
    
    card_id = await db.add_card(
        name=data['card_name'],
        rarity=data['card_rarity'],
        image_url=data['card_image'],
        description=data['card_description'],
        video_url=video_url
    )
    
    await message.answer(
        f"✅ Карточка добавлена!\n"
        f"ID: {card_id}\n"
        f"Название: {data['card_name']}\n"
        f"Редкость: {data['card_rarity'].value}"
    )
    
    await state.clear()

# === Запуск бота ===
async def main():
    await db.connect()
    # await start_web_server()  # Временно отключено
    logger.info("Starting bot...")
    await dp.start_polling(bot)
