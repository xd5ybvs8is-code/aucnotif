from datetime import UTC, datetime

from sqlalchemy import exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.auction_state import AuctionState
from app.models import Auction, UserAuction


class AuctionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_external_id(self, external_id: str) -> Auction | None:
        result = await self._session.execute(
            select(Auction).where(Auction.external_id == external_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, auction_id: int) -> Auction | None:
        return await self._session.get(Auction, auction_id)

    async def create(self, url: str, external_id: str, state: AuctionState) -> Auction:
        auction = Auction(
            external_id=external_id,
            url=url,
            title=state.title,
            current_price=state.current_price,
            bid_count=state.bid_count,
            start_time=state.start_time,
            end_time=state.end_time,
            buy_now_price=state.buy_now_price,
            quantity=state.quantity,
            is_store=state.is_store,
            is_closed=state.is_closed,
            has_winner=state.has_winner,
            monitoring_active=not state.is_closed,
            next_poll_at=datetime.now(UTC),
            last_polled_at=datetime.now(UTC),
        )
        self._session.add(auction)
        await self._session.flush()
        return auction

    async def update_from_state(self, auction: Auction, state: AuctionState) -> None:
        auction.title = state.title
        auction.current_price = state.current_price
        auction.bid_count = state.bid_count
        auction.start_time = state.start_time
        auction.end_time = state.end_time
        auction.buy_now_price = state.buy_now_price
        auction.quantity = state.quantity
        auction.is_store = state.is_store
        auction.is_closed = state.is_closed
        auction.has_winner = state.has_winner
        auction.last_polled_at = state.observed_at
        await self._session.flush()

    async def set_next_poll_at(self, auction_id: int, dt: datetime) -> None:
        await self._session.execute(
            update(Auction).where(Auction.id == auction_id).values(next_poll_at=dt)
        )

    async def stop_monitoring(self, auction_id: int) -> None:
        await self._session.execute(
            update(Auction)
            .where(Auction.id == auction_id)
            .values(monitoring_active=False, next_poll_at=None)
        )

    async def resume_monitoring(self, auction_id: int) -> None:
        await self._session.execute(
            update(Auction)
            .where(Auction.id == auction_id)
            .values(monitoring_active=True, next_poll_at=datetime.now(UTC))
        )

    async def record_error(
        self, auction_id: int, error_message: str, next_poll_at: datetime
    ) -> int:
        """Регистрирует ошибку, инкрементирует счётчик и возвращает новое значение."""
        auction = await self.get_by_id(auction_id)
        if auction is None:
            return 0
        auction.consecutive_errors += 1
        auction.last_error = error_message[:1000]
        auction.next_poll_at = next_poll_at
        await self._session.flush()
        return auction.consecutive_errors

    async def clear_error(self, auction_id: int) -> None:
        auction = await self.get_by_id(auction_id)
        if auction is not None:
            auction.consecutive_errors = 0
            auction.last_error = None
            await self._session.flush()

    async def list_due(self, now: datetime, limit: int = 200) -> list[Auction]:
        result = await self._session.execute(
            select(Auction)
            .where(
                Auction.monitoring_active.is_(True),
                Auction.is_closed.is_(False),
                Auction.next_poll_at.is_not(None),
                Auction.next_poll_at <= now,
            )
            .order_by(Auction.next_poll_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_active(self) -> list[Auction]:
        result = await self._session.execute(
            select(Auction).where(Auction.monitoring_active.is_(True))
        )
        return list(result.scalars().all())

    async def list_stale_monitoring(self, limit: int = 200) -> list[Auction]:
        """Аукционы, у которых не осталось подписчиков, но мониторинг ещё идёт."""
        result = await self._session.execute(
            select(Auction)
            .where(
                Auction.monitoring_active.is_(True),
                ~exists(
                    select(UserAuction.id).where(UserAuction.auction_id == Auction.id)
                ),
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_monitored(self) -> int:
        result = await self._session.execute(
            select(Auction.id).where(Auction.monitoring_active.is_(True))
        )
        return len(result.scalars().all())
