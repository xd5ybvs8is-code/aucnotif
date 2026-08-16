from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Auction, SentNotification, User, UserAuction


class UserAuctionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: int, auction_id: int) -> UserAuction | None:
        result = await self._session.execute(
            select(UserAuction).where(
                UserAuction.user_id == user_id,
                UserAuction.auction_id == auction_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(self, user_id: int, auction_id: int) -> UserAuction:
        link = UserAuction(user_id=user_id, auction_id=auction_id)
        self._session.add(link)
        await self._session.flush()
        return link

    async def delete(self, user_id: int, auction_id: int) -> bool:
        link = await self.get(user_id, auction_id)
        if link is None:
            return False
        await self._session.delete(link)
        await self._session.flush()
        return True

    async def count_watchers(self, auction_id: int) -> int:
        result = await self._session.execute(
            select(UserAuction.id).where(UserAuction.auction_id == auction_id)
        )
        return len(result.scalars().all())

    async def list_watchers(self, auction_id: int) -> list[tuple[User, UserAuction]]:
        """(user, link) для всех подписчиков аукциона с включёнными уведомлениями."""
        result = await self._session.execute(
            select(User, UserAuction)
            .join(UserAuction, UserAuction.user_id == User.id)
            .where(
                UserAuction.auction_id == auction_id,
                UserAuction.notifications_enabled.is_(True),
                User.is_active.is_(True),
            )
        )
        return [(user, link) for user, link in result.all()]

    async def list_for_user(self, user_id: int) -> list[tuple[UserAuction, Auction]]:
        result = await self._session.execute(
            select(UserAuction)
            .options(selectinload(UserAuction.auction))
            .where(UserAuction.user_id == user_id)
            .order_by(UserAuction.created_at.desc())
        )
        return [(link, link.auction) for link in result.scalars().unique().all()]

    async def delete_links_for_finalized_auctions(self) -> int:
        """Удаляет связки пользователей с завершёнными аукционами.

        Связка удаляется только если у неё не осталось pending-уведомлений —
        финальное уведомление о закрытии успеет дойти до пользователя.
        """
        closed_auction_ids = select(Auction.id).where(Auction.is_closed.is_(True))
        pending_notification = exists(
            select(SentNotification.id).where(
                SentNotification.user_auction_id == UserAuction.id,
                SentNotification.status == "pending",
            )
        )
        result = await self._session.execute(
            delete(UserAuction).where(
                UserAuction.auction_id.in_(closed_auction_ids),
                ~pending_notification,
            )
        )
        await self._session.flush()
        return result.rowcount

    async def set_notifications_enabled(self, user_id: int, auction_id: int, enabled: bool) -> bool:
        link = await self.get(user_id, auction_id)
        if link is None:
            return False
        link.notifications_enabled = enabled
        await self._session.flush()
        return True
