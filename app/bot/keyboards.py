from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

MENU_BACK_BUTTON = InlineKeyboardButton(text="🔙 В меню", callback_data="menu:home")

COMMON_OFFSETS = ("-8", "-5", "0", "+1", "+2", "+3", "+4", "+5", "+6", "+9", "+11")


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Мои аукционы", callback_data="menu:list")],
            [InlineKeyboardButton(text="➕ Добавить аукцион", callback_data="menu:add")],
            [InlineKeyboardButton(text="🕐 Часовой пояс", callback_data="menu:tz")],
            [InlineKeyboardButton(text="❓ Справка", callback_data="menu:help")],
        ]
    )


def back_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[MENU_BACK_BUTTON]])


def timezone_kb() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"UTC{offset}",
                callback_data=f"tz:UTC{offset}",
            )
            for offset in COMMON_OFFSETS[i : i + 4]
        ]
        for i in range(0, len(COMMON_OFFSETS), 4)
    ]
    rows.append([InlineKeyboardButton(text="✍️ Ввести вручную", callback_data="tz:manual")])
    rows.append([MENU_BACK_BUTTON])
    return InlineKeyboardMarkup(inline_keyboard=rows)
