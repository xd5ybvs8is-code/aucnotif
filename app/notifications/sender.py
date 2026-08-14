import asyncio

import structlog
from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramForbiddenError,
    TelegramRetryAfter,
)

from app.config import Settings
from app.infrastructure.metrics import NOTIFICATIONS_FAILED, NOTIFICATIONS_SENT, TELEGRAM_SEND_ERRORS
from app.models import SentNotification

logger = structlog.get_logger(__name__)

RETRYABLE_EXCEPTIONS = (TelegramRetryAfter,)


class TelegramSender:
    def __init__(self, bot: Bot, settings: Settings) -> None:
        self._bot = bot
        self._settings = settings
        self._semaphore = asyncio.Semaphore(20)

    async def send(self, notification: SentNotification, telegram_id: int) -> None:
        if notification.text is None:
            raise ValueError(f"notification {notification.id} has no text")

        attempt = 0
        while True:
            attempt += 1
            try:
                async with self._semaphore:
                    await self._bot.send_message(
                        chat_id=telegram_id,
                        text=notification.text,
                        disable_web_page_preview=True,
                    )
                NOTIFICATIONS_SENT.labels(kind=notification.kind).inc()
                return
            except TelegramRetryAfter as exc:
                retry_after = max(exc.retry_after, 1)
                TELEGRAM_SEND_ERRORS.labels(type="flood").inc()
                logger.warning(
                    "telegram_flood_control",
                    notification_id=notification.id,
                    retry_after=retry_after,
                )
                if attempt > self._settings.telegram_send_max_retries:
                    NOTIFICATIONS_FAILED.labels(kind=notification.kind).inc()
                    raise
                await asyncio.sleep(retry_after)
            except TelegramForbiddenError:
                TELEGRAM_SEND_ERRORS.labels(type="forbidden").inc()
                NOTIFICATIONS_FAILED.labels(kind=notification.kind).inc()
                logger.info("telegram_forbidden", telegram_id=telegram_id)
                raise
            except TelegramAPIError as exc:
                TELEGRAM_SEND_ERRORS.labels(type="api").inc()
                logger.warning("telegram_api_error", error=str(exc))
                if attempt > self._settings.telegram_send_max_retries:
                    NOTIFICATIONS_FAILED.labels(kind=notification.kind).inc()
                    raise
                await asyncio.sleep(
                    min(
                        self._settings.telegram_send_retry_base_seconds * (2 ** (attempt - 1)),
                        120,
                    )
                )
