from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_main_keyboard(is_premium: bool = False) -> ReplyKeyboardMarkup:
    """Главная клавиатура"""
    buttons = [
        [KeyboardButton(text="🎴 Найти карточку")],
        [KeyboardButton(text="📚 Моя коллекция"), KeyboardButton(text="👤 Профиль")],
        [KeyboardButton(text="🏆 Топ игроков"), KeyboardButton(text="⭐ Ежедневный бонус")],
    ]
    
    if is_premium:
        buttons.append([KeyboardButton(text="💎 Премиум активен")])
    else:
        buttons.append([KeyboardButton(text="💎 Купить премиум")])
    
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_collection_keyboard(page: int, total_pages: int, has_prev: bool, has_next: bool) -> InlineKeyboardMarkup:
    """Клавиатура для пагинации коллекции"""
    builder = InlineKeyboardBuilder()
    
    if has_prev:
        builder.button(text="◀️ Назад", callback_data=f"collection_page_{page - 1}")
    if has_next:
        builder.button(text="Вперед ▶️", callback_data=f"collection_page_{page + 1}")
    
    builder.button(text="🔄 Обновить", callback_data="refresh_collection")
    builder.button(text="🏠 Главное меню", callback_data="main_menu")
    
    builder.adjust(2, 1)
    return builder.as_markup()

def get_premium_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для покупки премиума"""
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 7 дней - 50⭐", callback_data="premium_7")
    builder.button(text="📅 30 дней - 150⭐", callback_data="premium_30")
    builder.button(text="📅 90 дней - 400⭐", callback_data="premium_90")
    builder.button(text="🔙 Назад", callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()

def get_confirm_premium_keyboard(days: int, price: int) -> InlineKeyboardMarkup:
    """Подтверждение покупки премиума"""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data=f"confirm_premium_{days}_{price}")
    builder.button(text="❌ Отмена", callback_data="premium_cancel")
    builder.adjust(2)
    return builder.as_markup()

def get_admin_keyboard() -> InlineKeyboardMarkup:
    """Админ-клавиатура"""
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить карточку", callback_data="admin_add_card")
    builder.button(text="📋 Список карточек", callback_data="admin_list_cards")
    builder.button(text="👑 Выдать премиум", callback_data="admin_give_premium")
    builder.button(text="📊 Статистика", callback_data="admin_stats")
    builder.button(text="🔙 Назад", callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()