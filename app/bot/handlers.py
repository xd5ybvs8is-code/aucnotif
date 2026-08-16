from contextlib import asynccontextmanager

from aiogram import Dispatcher, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.bot.keyboards import back_menu_kb, main_menu_kb
from app.config import get_settings
from app.db import get_session_factory
from app.domain.time import format_price, format_remaining
from app.domain.validation import InvalidAuctionUrl
from app.infrastructure.container import get_worker_provider
from app.notifications.renderer import NotificationRenderer
from app.providers.base import (
    AntiBotError,
    AuctionGoneError,
    PageDataNotFoundError,
    PageDataParseError,
    RateLimitedError,
)
from app.services.auction_service import AuctionService
from app.services.state_mapper import state_from_auction

HELP_TEXT = (
    "Я отслеживаю аукционы Yahoo Auctions Japan.\n\n"
    "Управление — кнопками:\n"
    "📋 Мои аукционы — список отслеживаемых аукционов\n"
    "➕ Добавить аукцион — начать отслеживание\n\n"
    "Чтобы начать отслеживание, отправь мне ссылку на аукцион вида:\n"
    "https://page.auctions.yahoo.co.jp/jp/auction/XXXXX\n\n"
    "Уведомления: за 30, 15 и 5 минут до окончания, "
    "при каждой новой ставке и продлении аукциона.\n\n"
    "Команды на всякий случай: /list, /help, /watch &lt;ссылка&gt;"
)

MAIN_MENU_TEXT = "Что будем делать?"

EMPTY_LIST_TEXT = "Список пуст. Отправь ссылку на аукцион, чтобы начать отслеживание."


@asynccontextmanager
async def get_service():
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield AuctionService(session, get_worker_provider(), get_settings())


async def _edit_or_answer(callback: CallbackQuery, text: str, kb: InlineKeyboardMarkup) -> None:
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        await callback.message.answer(text, reply_markup=kb)


async def _list_content(service: AuctionService, telegram_id: int) -> tuple[str, InlineKeyboardMarkup] | None:
    result = await service.list_for_user(telegram_id)
    if result is None or not result[1]:
        return None
    user, items = result
    items = items[:20]
    lines = ["🎯 Отслеживаемые аукционы:", ""]
    keyboard_rows = []
    for link, auction in items:
        status = "🏁 завершён" if auction.is_closed else "👀 активен"
        lines.append(f"{len(keyboard_rows) + 1}. {auction.title or 'Без названия'} ({status})")
        if auction.current_price is not None:
            lines.append(f"   💴 {format_price(auction.current_price)}")
        if auction.end_time is not None and not auction.is_closed:
            lines.append(f"   ⏰ До конца: {format_remaining(auction.end_time)}")
        lines.append("")
        mute_label = "🔔 Включить" if not link.notifications_enabled else "🔕 Отключить"
        keyboard_rows.append(
            [
                InlineKeyboardButton(text="🔗 Открыть", url=auction.url),
                InlineKeyboardButton(
                    text=mute_label,
                    callback_data=f"mute:{auction.external_id}",
                ),
                InlineKeyboardButton(
                    text="🗑 Удалить",
                    callback_data=f"del:{auction.external_id}",
                ),
            ]
        )
    keyboard_rows.append([InlineKeyboardButton(text="🔙 В меню", callback_data="menu:home")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard_rows)


async def _show_list(service: AuctionService, telegram_id: int, target: Message | CallbackQuery) -> None:
    content = await _list_content(service, telegram_id)
    if content is None:
        await _send(target, EMPTY_LIST_TEXT, back_menu_kb())
        return
    text, kb = content
    await _send(target, text, kb)


async def _send(target: Message | CallbackQuery, text: str, kb: InlineKeyboardMarkup) -> None:
    if isinstance(target, CallbackQuery):
        await _edit_or_answer(target, text, kb)
    else:
        await target.answer(text, reply_markup=kb)


def register_handlers(dp: Dispatcher) -> None:
    router = Router(name="auctions")

    @router.message(CommandStart())
    async def cmd_start(message: Message) -> None:
        await message.answer(MAIN_MENU_TEXT, reply_markup=main_menu_kb())

    @router.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        await message.answer(HELP_TEXT, reply_markup=back_menu_kb())

    @router.message(Command("list"))
    async def cmd_list(message: Message) -> None:
        async with get_service() as service:
            await _show_list(service, message.from_user.id, message)

    @router.message(Command("watch"))
    async def cmd_watch(message: Message) -> None:
        url = (message.text or "").partition(" ")[2].strip()
        if not url:
            await message.answer("Формат: /watch &lt;ссылка на аукцион Yahoo&gt;")
            return
        await _handle_url(message, url)

    @router.message(F.text.startswith("http"))
    async def handle_url_message(message: Message) -> None:
        await _handle_url(message, message.text or "")

    async def _handle_url(message: Message, url: str) -> None:
        try:
            async with get_service() as service:
                result, _user = await service.add_watch(message.from_user.id, url)
        except InvalidAuctionUrl:
            await message.answer(
                "❌ Некорректная ссылка.\n"
                "Допустимы только ссылки вида:\n"
                "https://page.auctions.yahoo.co.jp/jp/auction/XXXXX"
            )
            return
        except RateLimitedError:
            await message.answer("⚠️ Yahoo временно недоступен (rate limit). Попробуйте позже.")
            return
        except AuctionGoneError:
            await message.answer("❌ Аукцион не найден. Возможно, он был удалён.")
            return
        except (PageDataParseError, PageDataNotFoundError, AntiBotError):
            await message.answer("⚠️ Не удалось получить данные аукциона. Попробуйте позже.")
            return

        if result.already_watched:
            await message.answer("ℹ️ Этот аукцион уже добавлен.")
            return

        auction = result.auction
        if auction.is_closed:
            await message.answer(
                f"🏁 Аукцион «{auction.title or 'Без названия'}» уже завершён и не будет отслеживаться."
            )
            return

        renderer = NotificationRenderer()
        await message.answer(renderer.render_added(state_from_auction(auction), auction.url))

    @router.callback_query(F.data == "menu:home")
    async def cb_menu(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await _edit_or_answer(callback, MAIN_MENU_TEXT, main_menu_kb())
        await callback.answer()

    @router.callback_query(F.data == "menu:list")
    async def cb_list(callback: CallbackQuery) -> None:
        async with get_service() as service:
            await _show_list(service, callback.from_user.id, callback)
        await callback.answer()

    @router.callback_query(F.data == "menu:add")
    async def cb_add(callback: CallbackQuery) -> None:
        await _edit_or_answer(
            callback,
            "Отправьте мне ссылку на аукцион вида:\n"
            "https://page.auctions.yahoo.co.jp/jp/auction/XXXXX",
            back_menu_kb(),
        )
        await callback.answer()

    @router.callback_query(F.data == "menu:help")
    async def cb_help(callback: CallbackQuery) -> None:
        await _edit_or_answer(callback, HELP_TEXT, back_menu_kb())
        await callback.answer()

    @router.callback_query(F.data.startswith("del:"))
    async def cb_delete(callback: CallbackQuery) -> None:
        external_id = callback.data.split(":", 1)[1]
        async with get_service() as service:
            result = await service.remove_watch(callback.from_user.id, external_id)
            if result == "removed":
                await callback.answer("Аукцион удалён из списка.")
                await _show_list(service, callback.from_user.id, callback)
            else:
                await callback.answer("Аукцион не найден в вашем списке.")

    @router.callback_query(F.data.startswith("mute:"))
    async def cb_mute(callback: CallbackQuery) -> None:
        external_id = callback.data.split(":", 1)[1]
        async with get_service() as service:
            toggled = await service.toggle_notifications(callback.from_user.id, external_id)
            if toggled is None:
                await callback.answer("Аукцион не найден.")
            elif toggled:
                await callback.answer("Уведомления включены.")
                await _show_list(service, callback.from_user.id, callback)
            else:
                await callback.answer("Уведомления отключены.")
                await _show_list(service, callback.from_user.id, callback)

    dp.include_router(router)
