import asyncio
import json
import logging
from typing import Protocol, cast

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

CACHE_TIMEOUT_SECONDS = 0.5


class AsyncRedisClient(Protocol):
    async def get(self, key: str) -> object: ...

    async def set(self, key: str, value: str, *, ex: int) -> object: ...

    async def aclose(self) -> None: ...


class CacheStore(Protocol):
    @property
    def enabled(self) -> bool: ...

    async def get(self, key: str) -> str | None: ...

    async def set(self, key: str, payload: str, *, ttl_seconds: int) -> bool: ...

    async def aclose(self) -> None: ...


class DisabledCache:
    """No-op cache used when REDIS_URL is absent or blank."""

    @property
    def enabled(self) -> bool:
        return False

    async def get(self, key: str) -> str | None:
        del key
        return None

    async def set(self, key: str, payload: str, *, ttl_seconds: int) -> bool:
        del key, payload, ttl_seconds
        return False

    async def aclose(self) -> None:
        return None


class RedisCache:
    """Best-effort Redis adapter that never exposes cache failures to callers."""

    def __init__(
        self,
        client: AsyncRedisClient,
        *,
        timeout_seconds: float = CACHE_TIMEOUT_SECONDS,
    ) -> None:
        self._client = client
        self._timeout_seconds = timeout_seconds

    @property
    def enabled(self) -> bool:
        return True

    async def get(self, key: str) -> str | None:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                value = await self._client.get(key)
            if value is None:
                return None
            if isinstance(value, bytes):
                payload = value.decode("utf-8")
            elif isinstance(value, str):
                payload = value
            else:
                raise TypeError("Redis cache value must be bytes or text")
            json.loads(payload)
            return payload
        except Exception as exc:
            _log_cache_miss("read", exc)
            return None

    async def set(self, key: str, payload: str, *, ttl_seconds: int) -> bool:
        try:
            if ttl_seconds <= 0:
                raise ValueError("cache TTL must be positive")
            json.loads(payload)
            async with asyncio.timeout(self._timeout_seconds):
                await self._client.set(key, payload, ex=ttl_seconds)
            return True
        except Exception as exc:
            _log_cache_miss("write", exc)
            return False

    async def aclose(self) -> None:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                await self._client.aclose()
        except Exception as exc:
            _log_cache_miss("close", exc)


def create_cache(
    redis_url: str | None,
    *,
    timeout_seconds: float = CACHE_TIMEOUT_SECONDS,
) -> CacheStore:
    if redis_url is None or not redis_url.strip():
        return DisabledCache()

    try:
        client = Redis.from_url(
            redis_url,
            socket_connect_timeout=timeout_seconds,
            socket_timeout=timeout_seconds,
            decode_responses=False,
        )
    except Exception as exc:
        _log_cache_miss("connect", exc)
        return DisabledCache()
    return RedisCache(cast(AsyncRedisClient, client), timeout_seconds=timeout_seconds)


def _log_cache_miss(operation: str, exc: Exception) -> None:
    logger.warning(
        "cache_unavailable operation=%s error_type=%s",
        operation,
        type(exc).__name__,
    )
