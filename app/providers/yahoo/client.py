import time

import httpx
import structlog

from app.config import Settings
from app.infrastructure.metrics import (
    YAHOO_REQUEST_ERRORS_TOTAL,
    YAHOO_REQUESTS_TOTAL,
    YAHOO_RESPONSE_LATENCY,
)
from app.providers.base import AntiBotError, AuctionGoneError, RateLimitedError

logger = structlog.get_logger(__name__)

ANTI_BOT_MARKERS = ("captcha", "security check", "challenge")


class YahooHttpClient:
    """Async HTTP-клиент к Yahoo Auctions с timeout, пулом и rate limiting."""

    def __init__(
        self,
        settings: Settings,
        rate_limiter,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._rate_limiter = rate_limiter
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(settings.yahoo_request_timeout),
            follow_redirects=True,
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
            headers={
                "User-Agent": settings.yahoo_user_agent,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "ja,en;q=0.8",
            },
        )

    async def fetch_html(self, url: str) -> str:
        await self._rate_limiter.acquire()
        start = time.monotonic()
        try:
            response = await self._client.get(url)
        except httpx.TimeoutException as exc:
            YAHOO_REQUEST_ERRORS_TOTAL.labels(type="timeout").inc()
            logger.warning("yahoo_request_timeout", url=url)
            raise RateLimitedError(0, "timeout") from exc
        except httpx.HTTPError as exc:
            YAHOO_REQUEST_ERRORS_TOTAL.labels(type="network").inc()
            logger.warning("yahoo_request_network_error", url=url, error=str(exc))
            raise AuctionGoneError(str(exc)) from exc
        finally:
            YAHOO_RESPONSE_LATENCY.observe(time.monotonic() - start)

        YAHOO_REQUESTS_TOTAL.labels(status=str(response.status_code)).inc()

        if response.status_code == 429:
            YAHOO_REQUEST_ERRORS_TOTAL.labels(type="rate_limited").inc()
            raise RateLimitedError(429, "rate limited")
        if response.status_code == 403:
            YAHOO_REQUEST_ERRORS_TOTAL.labels(type="forbidden").inc()
            raise RateLimitedError(403, "forbidden")
        if response.status_code in (404, 410):
            YAHOO_REQUEST_ERRORS_TOTAL.labels(type="not_found").inc()
            raise AuctionGoneError(f"auction not found: {response.status_code}")
        if response.status_code >= 500:
            YAHOO_REQUEST_ERRORS_TOTAL.labels(type="server_error").inc()
            raise RateLimitedError(response.status_code, "yahoo server error")
        if response.status_code != 200:
            YAHOO_REQUEST_ERRORS_TOTAL.labels(type="unexpected_status").inc()
            raise AuctionGoneError(f"unexpected status {response.status_code}")

        text = response.text
        lowered = text[:20_000].lower()
        if any(marker in lowered for marker in ANTI_BOT_MARKERS):
            YAHOO_REQUEST_ERRORS_TOTAL.labels(type="antibot").inc()
            raise AntiBotError("anti-bot page detected")

        return text

    async def close(self) -> None:
        await self._client.aclose()
