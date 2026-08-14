import time
from collections.abc import Coroutine
from typing import Any, Protocol


class RateLimiter(Protocol):
    def acquire(self) -> Coroutine[Any, Any, float]: ...


class InMemoryRateLimiter:
    """Простой token bucket в памяти — для dev и unit-тестов."""

    def __init__(self, rate: float, burst: int = 1) -> None:
        self.rate = rate
        self.tokens = float(burst)
        self.burst = burst
        self._last = time.monotonic()

    async def acquire(self) -> float:
        now = time.monotonic()
        self.tokens = min(self.burst, self.tokens + (now - self._last) * self.rate)
        self._last = now
        if self.tokens >= 1:
            self.tokens -= 1
            return 0.0
        return (1 - self.tokens) / self.rate
