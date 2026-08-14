import asyncio
import time

from redis.asyncio import Redis

from app.infrastructure.ratelimit import RateLimiter


class RedisRateLimiter:
    """Глобальный token bucket в Redis — общий лимит для всех workers.

    Используется Lua-скрипт для атомарности: несколько worker'ов делят
    один общий бюджет запросов к Yahoo.
    """

    _SCRIPT = """
local key = KEYS[1]
local rate = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local data = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])

if tokens == nil then
    tokens = capacity
    ts = now
else
    tokens = math.min(capacity, tokens + (now - ts) * rate)
end

if tokens >= 1 then
    tokens = tokens - 1
    redis.call('HSET', key, 'tokens', tokens, 'ts', now)
    redis.call('PEXPIRE', key, 60000)
    return {0, now}
end

local wait = (1 - tokens) / rate
redis.call('HSET', key, 'tokens', 0, 'ts', now + wait)
redis.call('PEXPIRE', key, 60000)
return {wait, now}
"""

    def __init__(self, redis: Redis, key: str, rate: float, burst: int = 1) -> None:
        self._redis = redis
        self._key = key
        self._rate = rate
        self._burst = burst
        self._script = redis.register_script(self._SCRIPT)

    async def acquire(self) -> float:
        wait, _ = await self._script(
            keys=[self._key], args=[self._rate, self._burst, time.time()]
        )
        return float(wait)


async def acquire_with_wait(limiter: RateLimiter, wait_timeout: float = 30.0) -> bool:
    """Ждёт разрешения rate limiter'а, но не дольше wait_timeout."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + wait_timeout
    while True:
        wait = await limiter.acquire()
        if wait <= 0:
            return True
        if loop.time() + wait > deadline:
            return False
        await asyncio.sleep(wait)
