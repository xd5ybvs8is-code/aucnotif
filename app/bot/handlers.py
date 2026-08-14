from contextlib import asynccontextmanager

from aiogram import Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.config import get_settings
from app.db import get_session_factory
from app.domain.time import format_price, format_user_time, is_valid_timezone
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
    "Отправь мне ссылку на аукцион вида:\n"
    "https://page.auctions.yahoo.co.jp/jp/auction/XXXXX\n\n"
    "Команды:\n"
    "/list — список отслеживаемых аукционов\n"
    "/timezone — посмотреть часовой пояс\n"
    "/timezone <часовой пояс> — сменить пояс, например /timezone Europe/Moscow\n"
    "/help — справка\n\n"
    "Уведомления: за 30, 15 и 5 минут до окончания, "
    "при каждой новой ставке и продлении аукциона."
)


@asynccontextmanager
async def get_service():
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield AuctionService(session, get_worker_provider(), get_settings())


def register_handlers(dp: Dispatcher) -> None:
    router = Router(name="auctions")

    @router.message(CommandStart())
    async def cmd_start(message: Message) -> None:
        await message.answer(HELP_TEXT)

    @router.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        await message.answer(HELP_TEXT)

    @router.message(Command("list"))
    async def cmd_list(message: Message) -> None:
        async with get_service() as service:
            result = await service.list_for_user(message.from_user.id)
        if result is None or not result[1]:
            await message.answer(
                "Список пуст. Отправь ссылку на аукцион, чтобы начать отслеживание."
            )
            return
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
                lines.append(f"   ⏰ {format_user_time(auction.end_time, user.timezone)}")
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
        await message.answer(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        )

    @router.message(Command("timezone"))
    async def cmd_timezone(message: Message) -> None:
        tz_name = (message.text or "").partition(" ")[2].strip()
        if not tz_name:
            async with get_service() as service:
                user = await service.get_user(message.from_user.id)
            if user is not None:
                await message.answer(
                    f"Текущий часовой пояс: {user.timezone}\n"
                    "Сменить: /timezone <часовой пояс>, например /timezone Europe/Berlin"
                )
            else:
                await message.answer(
                    "Часовой пояс пока не задан.\n"
                    "Сменить: /timezone <часовой пояс>, например /timezone Europe/Moscow"
                )
            return

        if not is_valid_timezone(tz_name):
            await message.answer(
                "❌ Неизвестный часовой пояс. Укажите название из базы IANA, "
                "например: /timezone Europe/Moscow"
            )
            return

        async with get_service() as service:
            await service.set_timezone(message.from_user.id, tz_name)
        await message.answer(f"✅ Часовой пояс установлен: {tz_name}")

    @router.message(Command("watch"))
    async def cmd_watch(message: Message) -> None:
        url = (message.text or "").partition(" ")[2].strip()
        if not url:
            await message.answer("Формат: /watch <ссылка на аукцион Yahoo>")
            return
        await _handle_url(message, url)

    @router.message(F.text.startswith("http"))
    async def handle_url_message(message: Message) -> None:
        await _handle_url(message, message.text or "")

    async def _handle_url(message: Message, url: str) -> None:
        try:
            async with get_service() as service:
                result, user = await service.add_watch(message.from_user.id, url)
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

        renderer = NotificationRenderer(user.timezone)
        await message.answer(renderer.render_added(state_from_auction(auction), auction.url))

    @router.callback_query(F.data.startswith("del:"))
    async def cb_delete(callback: CallbackQuery) -> None:
        external_id = callback.data.split(":", 1)[1]
        async with get_service() as service:
            result = await service.remove_watch(callback.from_user.id, external_id)
        if result == "removed":
            await callback.answer("Аукцион удалён из списка.")
        else:
            await callback.answer("Аукцион не найден в вашем списке.")
        await callback.message.edit_reply_markup(reply_markup=None)

    @router.callback_query(F.data.startswith("mute:"))
    async def cb_mute(callback: CallbackQuery) -> None:
        external_id = callback.data.split(":", 1)[1]
        async with get_service() as service:
            user = await service.users.get_by_telegram_id(callback.from_user.id)
            toggled = None
            if user is not None:
                auction = await service.auctions.get_by_external_id(external_id)
                if auction is not None:
                    link = await service.user_auctions.get(user.id, auction.id)
                    if link is not None:
                        new_value = not link.notifications_enabled
                        await service.user_auctions.set_notifications_enabled(
                            user.id, auction.id, new_value
                        )
                        await service._session.commit()
                        toggled = new_value
        if toggled is None:
            await callback.answer("Аукцион не найден.")
        elif toggled:
            await callback.answer("Уведомления включены.")
        else:
            await callback.answer("Уведомления отключены.")
        await callback.message.edit_reply_markup(reply_markup=None)

    dp.include_router(router)
