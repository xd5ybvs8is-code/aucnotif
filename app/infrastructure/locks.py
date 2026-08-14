import asyncio
import uuid

from redis.asyncio import Redis


class RedisLock:
    """Distributed lock на Redis с TTL и безопасным освобождением.

    Освобождает только если значение token'а совпадает — защита от случая,
    когда TTL истёк, другой worker взял лок, а первый его «освободил».
    """

    _RELEASE_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
else
    return 0
end
"""

    def __init__(self, redis: Redis, key: str, ttl_seconds: int, token: str | None = None) -> None:
        self._redis = redis
        self._key = key
        self._ttl = ttl_seconds
        self._token = token or uuid.uuid4().hex
        self._release_script = redis.register_script(self._RELEASE_SCRIPT)
        self._held = False

    @property
    def held(self) -> bool:
        return self._held

    async def acquire(self, blocking: bool = False, wait_timeout: float = 5.0) -> bool:
        if blocking:
            loop = asyncio.get_running_loop()
            deadline = loop.time() + wait_timeout
            while True:
                if await self._try_acquire():
                    return True
                if loop.time() >= deadline:
                    return False
                await asyncio.sleep(0.2)
        return await self._try_acquire()

    async def _try_acquire(self) -> bool:
        ok = await self._redis.set(self._key, self._token, nx=True, ex=self._ttl)
        self._held = bool(ok)
        return self._held

    async def release(self) -> bool:
        if not self._held:
            return False
        released = bool(await self._release_script(keys=[self._key], args=[self._token]))
        if released:
            self._held = False
        return released
