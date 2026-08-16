from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

MENU_BACK_BUTTON = InlineKeyboardButton(text="🔙 В меню", callback_data="menu:home")


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Мои аукционы", callback_data="menu:list")],
            [InlineKeyboardButton(text="➕ Добавить аукцион", callback_data="menu:add")],
            [InlineKeyboardButton(text="❓ Справка", callback_data="menu:help")],
        ]
    )


def back_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[MENU_BACK_BUTTON]])
