from typing import Protocol

from app.domain.auction_state import AuctionState


class ProviderError(Exception):
    """Базовая ошибка провайдера данных."""

    retryable: bool = False


class HttpError(ProviderError):
    def __init__(self, status: int, message: str = "") -> None:
        self.status = status
        super().__init__(f"HTTP {status}: {message}")


class RateLimitedError(HttpError):
    retryable = True


class AntiBotError(ProviderError):
    """Yahoo вернул CAPTCHA / anti-bot страницу. Обход не реализуем."""


class PageDataNotFoundError(ProviderError):
    retryable = True


class PageDataParseError(ProviderError):
    pass


class AuctionGoneError(ProviderError):
    """Аукцион удалён/недоступен."""


class AuctionDataProvider(Protocol):
    async def get_auction_state(self, url: str) -> AuctionState: ...
