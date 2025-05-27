from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

def main_menu_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📂 Загрузить фото")],
            [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="📦 Мои заказы")],
        ],
        resize_keyboard=True,
        is_persistent=True
    )
