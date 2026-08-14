from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.auction_state import AuctionState
from app.models import AuctionSnapshot


class SnapshotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_latest(self, auction_id: int) -> AuctionSnapshot | None:
        result = await self._session.execute(
            select(AuctionSnapshot)
            .where(AuctionSnapshot.auction_id == auction_id)
            .order_by(AuctionSnapshot.observed_at.desc(), AuctionSnapshot.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create(self, auction_id: int, state: AuctionState, raw_data: dict | None) -> AuctionSnapshot:
        snapshot = AuctionSnapshot(
            auction_id=auction_id,
            observed_at=state.observed_at,
            current_price=state.current_price,
            bid_count=state.bid_count,
            end_time=state.end_time,
            buy_now_price=state.buy_now_price,
            is_closed=state.is_closed,
            has_winner=state.has_winner,
            new_bid=state.new_bid,
            raw_data=raw_data,
        )
        self._session.add(snapshot)
        await self._session.flush()
        return snapshot

    async def purge_old(self, before: datetime) -> int:
        result = await self._session.execute(
            delete(AuctionSnapshot).where(AuctionSnapshot.observed_at < before)
        )
        return result.rowcount or 0
