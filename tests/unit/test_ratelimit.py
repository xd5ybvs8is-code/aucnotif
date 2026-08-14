import time

from app.infrastructure.ratelimit import InMemoryRateLimiter


async def test_in_memory_rate_limiter_blocks_over_rate():
    limiter = InMemoryRateLimiter(rate=1.0, burst=1)
    wait1 = await limiter.acquire()
    start = time.monotonic()
    wait2 = await limiter.acquire()
    elapsed = time.monotonic() - start
    assert wait1 == 0.0
    assert wait2 > 0.0
    assert elapsed < 1.0  # возвращает ожидание, не спит сам


async def test_acquire_with_wait_waits_until_allowed():
    from app.infrastructure.redis_rate_limit import acquire_with_wait

    limiter = InMemoryRateLimiter(rate=2.0, burst=1)
    await limiter.acquire()
    start = time.monotonic()
    ok = await acquire_with_wait(limiter, wait_timeout=5.0)
    elapsed = time.monotonic() - start
    assert ok
    assert elapsed >= 0.3


async def test_acquire_with_wait_timeout():
    from app.infrastructure.redis_rate_limit import acquire_with_wait

    limiter = InMemoryRateLimiter(rate=0.1, burst=1)
    await limiter.acquire()
    ok = await acquire_with_wait(limiter, wait_timeout=0.2)
    assert not ok
