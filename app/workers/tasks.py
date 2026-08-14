import structlog
from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db import get_session_factory
from app.infrastructure.container import get_worker_provider
from app.infrastructure.locks import RedisLock
from app.infrastructure.logging import new_correlation_id
from app.infrastructure.metrics import (
    NOTIFICATIONS_FAILED,
    POLLING_JOBS_FAILED,
    POLLING_JOBS_TOTAL,
)
from app.infrastructure.redis import get_redis
from app.models import SentNotification, UserAuction
from app.notifications.sender import TelegramSender
from app.repositories.notifications import NotificationRepository
from app.services.monitoring_service import MonitoringService

logger = structlog.get_logger(__name__)

_sender: TelegramSender | None = None


def _get_sender() -> TelegramSender:
    global _sender
    if _sender is None:
        settings = get_settings()
        _sender = TelegramSender(Bot(token=settings.telegram_bot_token), settings)
    return _sender


async def poll_auction(ctx: dict, auction_id: int) -> str:
    """Poll одного аукциона. Distributed lock гарантирует, что
    аукцион никогда не опрашивается двумя workers одновременно."""
    new_correlation_id()
    logger.info("poll_auction_started", auction_id=auction_id)
    POLLING_JOBS_TOTAL.labels(result="started").inc()

    settings = get_settings()
    redis = get_redis()
    lock = RedisLock(
        redis,
        key=f"auction:{auction_id}:poll-lock",
        ttl_seconds=settings.poll_lock_ttl_seconds,
    )
    if not await lock.acquire():
        logger.info("poll_auction_skipped_locked", auction_id=auction_id)
        POLLING_JOBS_TOTAL.labels(result="locked").inc()
        return "locked"

    try:
        session_factory = get_session_factory()
        async with session_factory() as session:
            service = MonitoringService(
                session,
                get_worker_provider(),
                settings,
                enqueue_send=lambda name, *args: ctx["redis"].enqueue_job(name, *args),
            )
            result = await service.poll(auction_id)
        POLLING_JOBS_TOTAL.labels(result=result).inc()
        return result
    except Exception as exc:
        POLLING_JOBS_FAILED.inc()
        POLLING_JOBS_TOTAL.labels(result="exception").inc()
        logger.exception("poll_auction_failed", auction_id=auction_id, error=str(exc))
        raise
    finally:
        await lock.release()


async def send_notification(ctx: dict, notification_id: int) -> str:
    """Отправка одного уведомления с ретраями. Идемпотентна по статусу."""
    new_correlation_id()
    redis = get_redis()

    session_factory = get_session_factory()
    async with session_factory() as session:
        repo = NotificationRepository(session)
        result = await session.execute(
            select(SentNotification)
            .options(
                selectinload(SentNotification.user_auction).selectinload(UserAuction.user)
            )
            .where(SentNotification.id == notification_id)
        )
        notification = result.scalar_one_or_none()
        if notification is None:
            logger.warning("notification_not_found", notification_id=notification_id)
            return "not_found"
        if notification.status == "sent":
            return "already_sent"

        user = notification.user_auction.user
        await session.commit()

    lock = RedisLock(
        redis,
        key=f"notification:{notification_id}:send-lock",
        ttl_seconds=60,
    )
    if not await lock.acquire():
        return "locked"

    try:
        sender = _get_sender()
        try:
            await sender.send(notification, user.telegram_id)
        except Exception:
            async with session_factory() as session:
                repo = NotificationRepository(session)
                await repo.mark_failed(notification_id)
                await session.commit()
            NOTIFICATIONS_FAILED.labels(kind=notification.kind).inc()
            logger.error("notification_send_failed", notification_id=notification_id)
            raise
        else:
            async with session_factory() as session:
                repo = NotificationRepository(session)
                await repo.mark_sent(notification_id)
                await session.commit()
        return "sent"
    finally:
        await lock.release()
