from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SentNotification


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def claim(self, user_auction_id: int, kind: str, dedup_key: str) -> SentNotification | None:
        """Идемпотентно создаёт запись уведомления.

        Возвращает None, если уведомление уже зарегистрировано
        (другой worker/retry/рестарт) — дублей не будет.
        Используется SAVEPOINT: конфликт по уникальному индексу
        откатывает только вставку, не весь батч.
        """
        row = SentNotification(
            user_auction_id=user_auction_id,
            kind=kind,
            dedup_key=dedup_key,
            status="pending",
            created_at=datetime.now(UTC),
        )
        try:
            async with self._session.begin_nested():
                self._session.add(row)
                await self._session.flush()
        except IntegrityError:
            return None
        return row

    async def mark_sent(self, notification_id: int) -> None:
        notification = await self._session.get(SentNotification, notification_id)
        if notification is not None:
            notification.status = "sent"
            notification.sent_at = datetime.now(UTC)
            await self._session.flush()

    async def mark_failed(self, notification_id: int) -> None:
        notification = await self._session.get(SentNotification, notification_id)
        if notification is not None:
            notification.status = "failed"
            await self._session.flush()

    async def get_by_id(self, notification_id: int) -> SentNotification | None:
        return await self._session.get(SentNotification, notification_id)

    async def pending_count(self) -> int:
        result = await self._session.execute(
            select(SentNotification.id).where(SentNotification.status == "pending")
        )
        return len(result.scalars().all())

    async def list_pending_older_than(self, cutoff: datetime) -> list[int]:
        result = await self._session.execute(
            select(SentNotification.id)
            .where(
                SentNotification.status == "pending",
                SentNotification.created_at < cutoff,
            )
            .order_by(SentNotification.created_at.asc())
            .limit(500)
        )
        return list(result.scalars().all())
