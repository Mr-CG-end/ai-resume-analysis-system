import asyncio
import logging
from collections.abc import Callable

import pytest

from app.services.redis_cache import DisabledCache, RedisCache, create_cache


class FakeRedis:
    def __init__(self) -> None:
        self.value: object = None
        self.get_error: Exception | None = None
        self.set_error: Exception | None = None
        self.close_error: Exception | None = None
        self.set_call: tuple[str, str, int] | None = None

    async def get(self, key: str) -> object:
        del key
        if self.get_error is not None:
            raise self.get_error
        return self.value

    async def set(self, key: str, value: str, *, ex: int) -> object:
        if self.set_error is not None:
            raise self.set_error
        self.set_call = (key, value, ex)
        return True

    async def aclose(self) -> None:
        if self.close_error is not None:
            raise self.close_error


@pytest.mark.asyncio
async def test_disabled_cache_is_a_silent_miss() -> None:
    cache = create_cache(None)

    assert isinstance(cache, DisabledCache)
    assert cache.enabled is False
    assert await cache.get("private-key") is None
    assert await cache.set("private-key", "{}", ttl_seconds=86_400) is False


@pytest.mark.parametrize("redis_url", [None, "", "   "])
def test_blank_redis_url_does_not_create_client(redis_url: str | None) -> None:
    assert isinstance(create_cache(redis_url), DisabledCache)


@pytest.mark.asyncio
async def test_get_decodes_valid_json_bytes() -> None:
    client = FakeRedis()
    client.value = b'{"cached":true}'
    cache = RedisCache(client)

    assert await cache.get("key") == '{"cached":true}'


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value",
    [None, b"\xff", b"not-json", object()],
)
async def test_missing_undecodable_bad_json_and_wrong_type_are_misses(value: object) -> None:
    client = FakeRedis()
    client.value = value
    cache = RedisCache(client)

    assert await cache.get("secret-key") is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_factory",
    [ConnectionError, TimeoutError, OSError, ValueError],
)
async def test_read_errors_are_misses(
    error_factory: Callable[[], Exception],
) -> None:
    client = FakeRedis()
    client.get_error = error_factory()

    assert await RedisCache(client).get("key") is None


@pytest.mark.asyncio
async def test_set_writes_json_with_ttl() -> None:
    client = FakeRedis()
    cache = RedisCache(client)

    assert await cache.set("key", '{"value":1}', ttl_seconds=86_400) is True
    assert client.set_call == ("key", '{"value":1}', 86_400)


@pytest.mark.asyncio
@pytest.mark.parametrize("payload,ttl", [("bad-json", 86_400), ("{}", 0)])
async def test_invalid_write_input_is_bypassed(payload: str, ttl: int) -> None:
    client = FakeRedis()

    assert await RedisCache(client).set("key", payload, ttl_seconds=ttl) is False
    assert client.set_call is None


@pytest.mark.asyncio
async def test_write_and_close_errors_are_bypassed() -> None:
    client = FakeRedis()
    client.set_error = ConnectionError()
    client.close_error = OSError()
    cache = RedisCache(client)

    assert await cache.set("key", "{}", ttl_seconds=1) is False
    await cache.aclose()


@pytest.mark.asyncio
async def test_operation_timeout_is_a_miss() -> None:
    class SlowRedis(FakeRedis):
        async def get(self, key: str) -> object:
            del key
            await asyncio.sleep(0.05)
            return b"{}"

    assert await RedisCache(SlowRedis(), timeout_seconds=0.001).get("key") is None


@pytest.mark.asyncio
async def test_warning_does_not_leak_key_payload_or_exception_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = FakeRedis()
    client.get_error = ConnectionError("redis://user:password@example/private")
    cache = RedisCache(client)

    with caplog.at_level(logging.WARNING):
        assert await cache.get("resume:private-hash") is None

    log_text = caplog.text
    assert "cache_unavailable operation=read error_type=ConnectionError" in log_text
    assert "password" not in log_text
    assert "private-hash" not in log_text
