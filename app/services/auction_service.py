from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.domain.auction_state import AuctionState
from app.domain.validation import extract_auction_id, validate_auction_url
from app.models import Auction, User
from app.providers import AuctionDataProvider
from app.repositories.auctions import AuctionRepository
from app.repositories.user_auctions import UserAuctionRepository
from app.repositories.users import UserRepository

logger = structlog.get_logger(__name__)


class AddAuctionResult:
    def __init__(self, auction: Auction, already_watched: bool) -> None:
        self.auction = auction
        self.already_watched = already_watched


class AuctionService:
    """Application service: добавление/удаление аукционов из watchlist.

    Telegram-хендлеры не знают про БД — только этот сервис.
    """

    def __init__(
        self,
        session: AsyncSession,
        provider: AuctionDataProvider,
        settings: Settings,
    ) -> None:
        self._session = session
        self._provider = provider
        self._settings = settings
        self.auctions = AuctionRepository(session)
        self.users = UserRepository(session)
        self.user_auctions = UserAuctionRepository(session)

    async def add_watch(self, telegram_id: int, url: str) -> tuple[AddAuctionResult, User]:
        canonical_url = validate_auction_url(url)
        external_id = extract_auction_id(canonical_url)

        user = await self.users.get_or_create(
            telegram_id,
            timezone=self._settings.default_timezone,
            language=self._settings.default_language,
        )

        auction = await self.auctions.get_by_external_id(external_id)
        if auction is None:
            state = await self._provider.get_auction_state(canonical_url)
            if state.auction_id != external_id:
                logger.warning(
                    "auction_id_mismatch",
                    url_external_id=external_id,
                    page_external_id=state.auction_id,
                )
            auction = await self.auctions.create(canonical_url, external_id, state)

        if auction.is_closed:
            # Завершённые аукционы не добавляются в watchlist и не мониторятся.
            await self._session.commit()
            return AddAuctionResult(auction, already_watched=False), user

        link = await self.user_auctions.get(user.id, auction.id)
        if link is not None:
            # Повторное добавление — не создаём дублей.
            await self._session.commit()
            return AddAuctionResult(auction, already_watched=True), user

        await self.user_auctions.create(user.id, auction.id)
        if not auction.monitoring_active and not auction.is_closed:
            await self.auctions.resume_monitoring(auction.id)
        await self._session.commit()
        logger.info(
            "auction_added",
            telegram_id=telegram_id,
            auction_id=auction.id,
            external_id=external_id,
        )
        return AddAuctionResult(auction, already_watched=False), user

    async def remove_watch(self, telegram_id: int, external_id: str) -> str:
        user = await self.users.get_by_telegram_id(telegram_id)
        if user is None:
            return "not_found"
        auction = await self.auctions.get_by_external_id(external_id)
        if auction is None:
            return "not_found"

        deleted = await self.user_auctions.delete(user.id, auction.id)
        if not deleted:
            return "not_found"

        watchers_left = await self.user_auctions.count_watchers(auction.id)
        if watchers_left == 0:
            # Grace period: не останавливаем мониторинг мгновенно, чтобы
            # не создавать race с повторным добавлением. Scheduler остановит
            # его по истечении grace period, если подписчиков нет.
            grace_until = datetime.now(UTC) + timedelta(
                seconds=self._settings.unwatch_grace_period_seconds
            )
            await self.auctions.set_next_poll_at(auction.id, grace_until)
        await self._session.commit()
        logger.info("auction_removed", telegram_id=telegram_id, auction_id=auction.id)
        return "removed"

    async def list_for_user(self, telegram_id: int) -> tuple[User, list[tuple]] | None:
        user = await self.users.get_by_telegram_id(telegram_id)
        if user is None:
            return None
        items = await self.user_auctions.list_for_user(user.id)
        return user, items

    async def toggle_notifications(self, telegram_id: int, external_id: str) -> bool | None:
        """Переключает уведомления для аукциона. Возвращает новое значение или None, если не найдено."""
        user = await self.users.get_by_telegram_id(telegram_id)
        if user is None:
            return None
        auction = await self.auctions.get_by_external_id(external_id)
        if auction is None:
            return None
        link = await self.user_auctions.get(user.id, auction.id)
        if link is None:
            return None
        new_value = not link.notifications_enabled
        await self.user_auctions.set_notifications_enabled(user.id, auction.id, new_value)
        await self._session.commit()
        return new_value

    async def set_timezone(self, telegram_id: int, timezone: str) -> User:
        user = await self.users.set_timezone(telegram_id, timezone)
        await self._session.commit()
        return user

    async def get_user(self, telegram_id: int) -> User | None:
        return await self.users.get_by_telegram_id(telegram_id)

    async def get_state(self, url: str) -> AuctionState:
        return await self._provider.get_auction_state(url)
