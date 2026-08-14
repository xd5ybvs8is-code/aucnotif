from app.config import get_settings
from app.infrastructure.redis import get_redis
from app.infrastructure.redis_rate_limit import RedisRateLimiter
from app.providers.yahoo.client import YahooHttpClient
from app.providers.yahoo.provider import YahooAuctionProvider

_provider: YahooAuctionProvider | None = None


def get_worker_provider() -> YahooAuctionProvider:
    """Process-global провайдер: общий httpx-пул и глобальный rate limiter."""
    global _provider
    if _provider is None:
        settings = get_settings()
        limiter = RedisRateLimiter(
            get_redis(),
            key="yahoo:rate-limit",
            rate=settings.yahoo_rate_limit,
            burst=1,
        )
        client = YahooHttpClient(settings, limiter)
        _provider = YahooAuctionProvider(client, store_raw_data=settings.store_raw_data)
    return _provider


async def close_worker_provider() -> None:
    global _provider
    if _provider is not None:
        await _provider.close()
    _provider = None
