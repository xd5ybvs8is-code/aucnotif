import asyncio

import pytest
from fakeredis import aioredis


@pytest.fixture
async def fake_redis():
    return aioredis.FakeRedis()


async def test_lock_acquire_and_release(fake_redis):
    from app.infrastructure.locks import RedisLock

    lock1 = RedisLock(fake_redis, "auction:1:poll-lock", ttl_seconds=10)
    lock2 = RedisLock(fake_redis, "auction:1:poll-lock", ttl_seconds=10)

    assert await lock1.acquire() is True
    assert lock1.held is True
    assert await lock2.acquire() is False  # второй worker не может взять лок

    assert await lock1.release() is True
    assert await lock2.acquire() is True  # после освобождения — можно
    await lock2.release()


async def test_lock_does_not_release_foreign_lock(fake_redis):
    from app.infrastructure.locks import RedisLock

    lock1 = RedisLock(fake_redis, "auction:1:poll-lock", ttl_seconds=10, token="tok-a")
    lock2 = RedisLock(fake_redis, "auction:1:poll-lock", ttl_seconds=10, token="tok-b")

    assert await lock1.acquire() is True
    assert await lock2.release() is False  # чужой токен не освобождает


async def test_lock_blocking_acquire(fake_redis):
    from app.infrastructure.locks import RedisLock

    lock1 = RedisLock(fake_redis, "auction:1:poll-lock", ttl_seconds=10)
    assert await lock1.acquire() is True

    async def release_soon():
        await asyncio.sleep(0.3)
        await lock1.release()

    task = asyncio.create_task(release_soon())
    lock2 = RedisLock(fake_redis, "auction:1:poll-lock", ttl_seconds=10)
    assert await lock2.acquire(blocking=True, wait_timeout=2.0) is True
    await task
