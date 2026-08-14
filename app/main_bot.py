import asyncio
import logging

import structlog
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from app.config import get_settings
from app.db import dispose_engine
from app.infrastructure.logging import setup_logging
from app.infrastructure.redis import close_redis

logger = structlog.get_logger(__name__)


async def main() -> None:
    setup_logging()
    settings = get_settings()

    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    sentry_enabled = bool(settings.sentry_dsn)
    if sentry_enabled:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.environment,
            traces_sample_rate=0.1,
        )
        logger.info("sentry_enabled")

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    dp = Dispatcher()

    from app.bot.handlers import register_handlers

    register_handlers(dp)

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("bot_started", mode="polling")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await dispose_engine()
        await close_redis()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("bot stopped")
