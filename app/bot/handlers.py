import math
from contextlib import asynccontextmanager

from aiogram import Dispatcher, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.bot.keyboards import back_menu_kb, main_menu_kb
from app.config import get_settings
from app.db import get_session_factory
from app.domain.time import JST, ensure_aware, format_price, format_remaining
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
    "https://page.auctions.yahoo.co.jp/jp/auction/XXXXX или\n"
    "https://auctions.yahoo.co.jp/jp/auction/XXXXX\n\n"
    "Уведомления: за 30, 15 и 5 минут до окончания, "
    "при каждой новой ставке и продлении аукциона.\n\n"
    "Команды на всякий случай: /list, /help, /watch &lt;ссылка&gt;"
)

MAIN_MENU_TEXT = "Что будем делать?"

EMPTY_LIST_TEXT = "Список пуст. Отправь ссылку на аукцион, чтобы начать отслеживание."

MAX_LABEL_LENGTH = 255

NAME_PROMPT_TEXT = "Как назвать этот аукцион? Отправь название или /skip, чтобы оставить название лота с Yahoo."


class NamingState(StatesGroup):
    waiting_for_name = State()


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


PAGE_SIZE = 9

LIST_HEADER_TEXT = "🎯 Отслеживаемые аукционы:"


def _format_dt(dt) -> str | None:
    aware = ensure_aware(dt)
    if aware is None:
        return None
    return aware.astimezone(JST).strftime("%Y-%m-%d %H:%M")


def _auction_text(link, auction) -> str:
    title = link.label or auction.title or "Без названия"
    status = "🏁 завершён" if auction.is_closed else "👀 активен"
    lines = [f"🎮 {title}", f"Статус: {status}", ""]
    if auction.current_price is not None:
        lines.append(f"💴 Текущая ставка: {format_price(auction.current_price)}")
    if auction.bid_count is not None:
        lines.append(f"👥 Ставок: {auction.bid_count}")
    if auction.buy_now_price is not None:
        lines.append(f"🛒 Купить сейчас: {format_price(auction.buy_now_price)}")
    if auction.quantity is not None:
        lines.append(f"📦 Количество: {auction.quantity}")
    if auction.is_store is not None:
        lines.append(f"🏪 Магазин: {'да' if auction.is_store else 'нет'}")
    start = _format_dt(auction.start_time)
    if start is not None:
        lines.append(f"🕐 Начало (JST): {start}")
    if auction.end_time is not None:
        if not auction.is_closed:
            lines.append(f"⏰ До конца: {format_remaining(auction.end_time)}")
        end = _format_dt(auction.end_time)
        if end is not None:
            lines.append(f"🕐 Окончание (JST): {end}")
    if auction.is_closed and auction.has_winner is not None:
        lines.append("✅ Победитель определён" if auction.has_winner else "❌ Победитель не определён")
    return "\n".join(lines)


def _auction_submenu(link, auction, page: int) -> tuple[str, InlineKeyboardMarkup]:
    mute_label = "🔕 Отключить" if link.notifications_enabled else "🔔 Включить"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Открыть", url=auction.url)],
            [
                InlineKeyboardButton(
                    text=mute_label,
                    callback_data=f"mute:{auction.external_id}:{page}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Удалить",
                    callback_data=f"del:{auction.external_id}:{page}",
                )
            ],
            [InlineKeyboardButton(text="🔙 Назад", callback_data=f"list:page:{page}")],
        ]
    )
    return _auction_text(link, auction), kb


async def _list_content(
    service: AuctionService, telegram_id: int, page: int = 1
) -> tuple[str, InlineKeyboardMarkup] | None:
    result = await service.list_for_user(telegram_id)
    if result is None or not result[1]:
        return None
    _user, items = result
    total_pages = max(1, math.ceil(len(items) / PAGE_SIZE))
    page = max(1, min(page, total_pages))
    start = (page - 1) * PAGE_SIZE
    page_items = items[start : start + PAGE_SIZE]

    keyboard_rows = []
    for link, auction in page_items:
        title = link.label or auction.title or "Без названия"
        keyboard_rows.append(
            [InlineKeyboardButton(text=title, callback_data=f"auction:{auction.external_id}:{page}")]
        )

    nav = []
    if total_pages > 1:
        if page > 1:
            nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"list:page:{page - 1}"))
        nav.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
        if page < total_pages:
            nav.append(InlineKeyboardButton(text="➡️", callback_data=f"list:page:{page + 1}"))
    nav.append(InlineKeyboardButton(text="🔙 В меню", callback_data="menu:home"))
    keyboard_rows.append(nav)

    return LIST_HEADER_TEXT, InlineKeyboardMarkup(inline_keyboard=keyboard_rows)


async def _show_list(
    service: AuctionService, telegram_id: int, target: Message | CallbackQuery, page: int = 1
) -> None:
    content = await _list_content(service, telegram_id, page)
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
    async def cmd_watch(message: Message, state: FSMContext) -> None:
        url = (message.text or "").partition(" ")[2].strip()
        if not url:
            await message.answer("Формат: /watch &lt;ссылка на аукцион Yahoo&gt;")
            return
        await _handle_url(message, url, state)

    @router.message(F.text.startswith("http"))
    async def handle_url_message(message: Message, state: FSMContext) -> None:
        await _handle_url(message, message.text or "", state)

    async def _handle_url(message: Message, url: str, state: FSMContext) -> None:
        await state.clear()
        try:
            async with get_service() as service:
                result, _user = await service.add_watch(message.from_user.id, url)
        except InvalidAuctionUrl:
            await message.answer(
                "❌ Некорректная ссылка.\n"
                "Допустимы только ссылки вида:\n"
                "https://page.auctions.yahoo.co.jp/jp/auction/XXXXX или\n"
                "https://auctions.yahoo.co.jp/jp/auction/XXXXX"
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
        await state.set_state(NamingState.waiting_for_name)
        await state.update_data(external_id=auction.external_id)
        await message.answer(NAME_PROMPT_TEXT)

    @router.message(NamingState.waiting_for_name, Command("skip", "cancel"))
    async def cmd_skip_name(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer("Ок, оставлю название лота с Yahoo.")

    @router.message(NamingState.waiting_for_name, F.text)
    async def handle_name_message(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        external_id = data.get("external_id")
        label = (message.text or "").strip()[:MAX_LABEL_LENGTH] or None
        if not external_id:
            await state.clear()
            await message.answer("Что-то пошло не так. Добавьте аукцион заново.")
            return
        async with get_service() as service:
            result = await service.set_label(message.from_user.id, external_id, label)
        await state.clear()
        if result is None:
            await message.answer("Аукцион не найден в вашем списке.")
        elif label:
            await message.answer(f"✅ Название сохранено: «{label}».")
        else:
            await message.answer("Ок, оставлю название лота с Yahoo.")

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

    @router.callback_query(F.data.startswith("list:page:"))
    async def cb_list_page(callback: CallbackQuery) -> None:
        page = int(callback.data.split(":", 2)[2])
        async with get_service() as service:
            await _show_list(service, callback.from_user.id, callback, page)
        await callback.answer()

    @router.callback_query(F.data == "noop")
    async def cb_noop(callback: CallbackQuery) -> None:
        await callback.answer()

    @router.callback_query(F.data == "menu:add")
    async def cb_add(callback: CallbackQuery) -> None:
        await _edit_or_answer(
            callback,
            "Отправьте мне ссылку на аукцион вида:\n"
            "https://page.auctions.yahoo.co.jp/jp/auction/XXXXX или\n"
            "https://auctions.yahoo.co.jp/jp/auction/XXXXX",
            back_menu_kb(),
        )
        await callback.answer()

    @router.callback_query(F.data == "menu:help")
    async def cb_help(callback: CallbackQuery) -> None:
        await _edit_or_answer(callback, HELP_TEXT, back_menu_kb())
        await callback.answer()

    @router.callback_query(F.data.startswith("auction:"))
    async def cb_auction(callback: CallbackQuery) -> None:
        _prefix, external_id, page = callback.data.split(":", 2)
        page = int(page)
        async with get_service() as service:
            item = await service.get_watch_item(callback.from_user.id, external_id)
            if item is None:
                await callback.answer("Аукцион не найден.")
                return
            text, kb = _auction_submenu(*item, page)
            await _edit_or_answer(callback, text, kb)
        await callback.answer()

    @router.callback_query(F.data.startswith("del:"))
    async def cb_delete(callback: CallbackQuery) -> None:
        _prefix, external_id, page = callback.data.split(":", 2)
        page = int(page)
        async with get_service() as service:
            result = await service.remove_watch(callback.from_user.id, external_id)
            if result == "removed":
                await callback.answer("Аукцион удалён из списка.")
                await _show_list(service, callback.from_user.id, callback, page)
            else:
                await callback.answer("Аукцион не найден в вашем списке.")

    @router.callback_query(F.data.startswith("mute:"))
    async def cb_mute(callback: CallbackQuery) -> None:
        _prefix, external_id, page = callback.data.split(":", 2)
        page = int(page)
        async with get_service() as service:
            toggled = await service.toggle_notifications(callback.from_user.id, external_id)
            if toggled is None:
                await callback.answer("Аукцион не найден.")
                return
            await callback.answer("Уведомления включены." if toggled else "Уведомления отключены.")
            item = await service.get_watch_item(callback.from_user.id, external_id)
            if item is None:
                await _show_list(service, callback.from_user.id, callback, page)
                return
            text, kb = _auction_submenu(*item, page)
            await _edit_or_answer(callback, text, kb)

    dp.include_router(router)
