import asyncio
from datetime import UTC, datetime, timedelta

import structlog
from arq import create_pool
from arq.connections import RedisSettings

from app.config import get_settings
from app.db import dispose_engine, get_session_factory
from app.infrastructure.locks import RedisLock
from app.infrastructure.logging import new_correlation_id, setup_logging
from app.infrastructure.metrics import AUCTIONS_MONITORED, QUEUE_SIZE
from app.infrastructure.redis import close_redis, get_redis
from app.repositories.auctions import AuctionRepository
from app.repositories.notifications import NotificationRepository
from app.repositories.snapshots import SnapshotRepository
from app.repositories.user_auctions import UserAuctionRepository

logger = structlog.get_logger(__name__)

PENDING_RECOVERY_DELAY = timedelta(minutes=5)


class Scheduler:
    """Отдельный лёгкий процесс: сканирует due-аукционы и ставит poll jobs.

    Истина — в PostgreSQL: после рестарта scheduler восстанавливает работу
    из due-списка без какого-либо in-memory состояния.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._redis_settings = RedisSettings.from_dsn(self._settings.redis_url)

    async def run_forever(self) -> None:
        arq_pool = await create_pool(self._redis_settings)
        try:
            while True:
                try:
                    await self.tick(arq_pool)
                except Exception:
                    logger.exception("scheduler_tick_failed")
                await asyncio.sleep(self._settings.scheduler_tick_seconds)
        finally:
            await arq_pool.aclose()

    async def tick(self, arq_pool) -> None:
        new_correlation_id()
        tick_lock = RedisLock(
            get_redis(),
            key="scheduler:tick-lock",
            ttl_seconds=max(self._settings.scheduler_tick_seconds, 10),
        )
        if not await tick_lock.acquire():
            return  # другой экземпляр scheduler'а уже работает
        try:
            await self._tick(arq_pool)
        finally:
            await tick_lock.release()

    async def _tick(self, arq_pool) -> None:
        now = datetime.now(UTC)
        session_factory = get_session_factory()
        async with session_factory() as session:
            auctions_repo = AuctionRepository(session)
            user_auctions_repo = UserAuctionRepository(session)

            due = await auctions_repo.list_due(now)
            for auction in due:
                watchers = await user_auctions_repo.count_watchers(auction.id)
                if watchers == 0:
                    # Последний подписчик ушёл, grace period истёк — останавливаем.
                    logger.info("stopping_monitoring_no_watchers", auction_id=auction.id)
                    await auctions_repo.stop_monitoring(auction.id)
                    continue
                await arq_pool.enqueue_job("poll_auction", auction.id)
                # Защита от повторного enqueue раньше, чем закончится lock.
                await auctions_repo.set_next_poll_at(
                    auction.id, now + timedelta(seconds=self._settings.poll_lock_ttl_seconds)
                )

            removed = await user_auctions_repo.delete_links_for_finalized_auctions()
            if removed:
                logger.info("closed_watchlist_cleaned", removed=removed)

            await self.recover_pending_notifications(session, arq_pool)
            await self.purge_old_snapshots(session)

            monitored = await auctions_repo.count_monitored()
            AUCTIONS_MONITORED.set(monitored)
            await session.commit()

        await self._update_queue_size(arq_pool)

    async def purge_old_snapshots(self, session) -> None:
        """Ежедневная очистка старых snapshots (retention)."""
        retention = self._settings.snapshot_retention_days
        if retention <= 0:
            return
        try:
            redis = get_redis()
            last_run = await redis.get("retention:snapshots:last-run")
            now = datetime.now(UTC)
            if last_run is not None and (now - datetime.fromisoformat(last_run)) < timedelta(hours=23):
                return
            cutoff = now - timedelta(days=retention)
            removed = await SnapshotRepository(session).purge_old(cutoff)
            await redis.set("retention:snapshots:last-run", now.isoformat(), ex=86400)
            if removed:
                logger.info("snapshots_purged", removed=removed)
        except Exception:
            logger.warning("snapshot_purge_failed", exc_info=True)

    async def recover_pending_notifications(self, session, arq_pool) -> None:
        """Crash-safety: повторно ставим в очередь pending-уведомления.

        Идемпотентность гарантируется уникальным ключом sent_notifications
        и проверкой статуса в send_notification.
        """
        repo = NotificationRepository(session)
        cutoff = datetime.now(UTC) - PENDING_RECOVERY_DELAY
        pending = await repo.list_pending_older_than(cutoff)
        for notification_id in pending:
            await arq_pool.enqueue_job("send_notification", notification_id)
        if pending:
            logger.info("pending_notifications_reenqueued", count=len(pending))

    async def _update_queue_size(self, arq_pool) -> None:
        try:
            redis = get_redis()
            queue_name = "arq:queue"
            size = await redis.llen(f"arq:queue:{queue_name}")
            QUEUE_SIZE.labels(queue=queue_name).set(size or 0)
        except Exception:
            logger.warning("queue_size_update_failed", exc_info=True)


async def main() -> None:
    setup_logging()
    scheduler = Scheduler()
    logger.info("scheduler_started", tick_seconds=get_settings().scheduler_tick_seconds)
    try:
        await scheduler.run_forever()
    finally:
        await dispose_engine()
        await close_redis()


if __name__ == "__main__":
    asyncio.run(main())
