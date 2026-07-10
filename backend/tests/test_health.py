from collections.abc import Awaitable, Callable
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from starlette.requests import ClientDisconnect, Request
from starlette.responses import Response
from starlette.routing import Route, Router
from starlette.types import Message, Scope

from app.api.routes import health as health_module
from app.core.config import Settings
from app.core.request_id import RequestIdMiddleware
from app.main import app

RedisPing = Callable[[str], Awaitable[bool]]


def _configured_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "ai_api_key": "test-key",
        "ai_base_url": "https://ai.example.test/v1",
        "ai_model": "test-model",
    }
    values.update(overrides)
    return Settings(**values)


async def _request_health(
    *,
    settings: Settings,
    redis_ping: RedisPing | None = None,
    request_id: str | None = None,
) -> httpx.Response:
    app.dependency_overrides[health_module.get_settings] = lambda: settings
    redis_ping_dependency = getattr(health_module, "get_redis_ping", None)
    if redis_ping_dependency is not None and redis_ping is not None:
        app.dependency_overrides[redis_ping_dependency] = lambda: redis_ping

    headers = {"X-Request-ID": request_id} if request_id is not None else None
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/api/v1/health", headers=headers)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_health_is_unavailable_when_ai_is_missing() -> None:
    response = await _request_health(settings=Settings(_env_file=None))

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "version": "0.1.0",
        "dependencies": {"ai": "unavailable", "redis": "disabled"},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "settings",
    [
        Settings(_env_file=None, ai_api_key="test-key"),
        Settings(
            _env_file=None,
            ai_api_key="test-key",
            ai_base_url="https://ai.example.test/v1",
        ),
        Settings(
            _env_file=None,
            ai_api_key="test-key",
            ai_model="test-model",
        ),
        Settings(
            _env_file=None,
            ai_api_key="",
            ai_base_url="",
            ai_model="",
        ),
    ],
)
async def test_health_is_unavailable_when_ai_configuration_is_partial(
    settings: Settings,
) -> None:
    response = await _request_health(settings=settings)

    assert response.status_code == 503
    assert response.json()["dependencies"]["ai"] == "unavailable"


@pytest.mark.asyncio
async def test_health_is_ok_when_ai_is_configured_and_redis_is_disabled() -> None:
    response = await _request_health(settings=_configured_settings(redis_url=None))

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": "0.1.0",
        "dependencies": {"ai": "configured", "redis": "disabled"},
    }


@pytest.mark.asyncio
async def test_health_reports_redis_up_after_successful_ping() -> None:
    async def redis_up(_: str) -> bool:
        return True

    response = await _request_health(
        settings=_configured_settings(redis_url="redis://example.test:6379/0"),
        redis_ping=redis_up,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["dependencies"] == {"ai": "configured", "redis": "up"}


@pytest.mark.asyncio
@pytest.mark.parametrize("redis_result", [False])
async def test_health_is_degraded_when_redis_ping_fails(redis_result: bool) -> None:
    async def redis_down(_: str) -> bool:
        return redis_result

    response = await _request_health(
        settings=_configured_settings(redis_url="redis://example.test:6379/0"),
        redis_ping=redis_down,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["dependencies"] == {"ai": "configured", "redis": "down"}


@pytest.mark.asyncio
async def test_redis_ping_uses_short_timeouts_and_closes_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ping_redis = getattr(health_module, "ping_redis", None)
    assert ping_redis is not None

    options: dict[str, float] = {}

    class FakeClient:
        closed = False

        async def ping(self) -> bool:
            raise TimeoutError

        async def aclose(self) -> None:
            self.closed = True

    client = FakeClient()

    class FakeRedis:
        @staticmethod
        def from_url(_: str, **kwargs: float) -> FakeClient:
            options.update(kwargs)
            return client

    monkeypatch.setattr(health_module, "Redis", FakeRedis)

    assert await ping_redis("redis://example.test:6379/0") is False
    assert 0 < options["socket_connect_timeout"] <= 1
    assert 0 < options["socket_timeout"] <= 1
    assert client.closed is True


@pytest.mark.asyncio
@pytest.mark.parametrize("redis_url", ["", "not-a-url"])
async def test_health_is_degraded_when_redis_url_is_empty_or_invalid(
    monkeypatch: pytest.MonkeyPatch,
    redis_url: str,
) -> None:
    class InvalidRedis:
        @staticmethod
        def from_url(_: str, **__: float) -> None:
            raise ValueError("invalid redis URL")

    monkeypatch.setattr(health_module, "Redis", InvalidRedis)

    response = await _request_health(settings=_configured_settings(redis_url=redis_url))

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["dependencies"] == {"ai": "configured", "redis": "down"}


@pytest.mark.asyncio
async def test_request_id_echoes_safe_incoming_value() -> None:
    response = await _request_health(
        settings=_configured_settings(),
        request_id="req.Safe_value-123",
    )

    assert response.headers["X-Request-ID"] == "req.Safe_value-123"


@pytest.mark.asyncio
@pytest.mark.parametrize("request_id", [None, "unsafe request id", "x" * 129])
async def test_request_id_generates_uuid_when_missing_or_invalid(request_id: str | None) -> None:
    response = await _request_health(settings=_configured_settings(), request_id=request_id)

    generated = response.headers["X-Request-ID"]
    assert str(UUID(generated)) == generated


@pytest.mark.asyncio
async def test_unhandled_server_error_uses_safe_contract_and_request_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from app.main import create_app

    test_app: FastAPI = create_app()

    @test_app.post("/test/unhandled")
    async def raise_unhandled_error() -> None:
        raise RuntimeError("secret-token=must-not-appear")

    transport = httpx.ASGITransport(app=test_app, raise_app_exceptions=True)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/test/unhandled",
            headers={"X-Request-ID": "req-unhandled-500"},
            content="resume-secret-body",
        )

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "req-unhandled-500"
    assert response.json() == {
        "error": {
            "code": "INTERNAL_SERVER_ERROR",
            "message": "服务器内部错误，请稍后重试。",
            "request_id": "req-unhandled-500",
            "details": {},
        }
    }
    assert any(
        record.getMessage() == "unhandled_request_error request_id=req-unhandled-500 method=POST"
        for record in caplog.records
    )
    assert "resume-secret-body" not in caplog.text
    assert "secret-token" not in caplog.text
    assert "must-not-appear" not in caplog.text
    assert "must-not-appear" not in response.text


@pytest.mark.asyncio
async def test_request_id_middleware_propagates_client_disconnect_without_response(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def read_request_body(request: Request) -> Response:
        await request.body()
        return Response(status_code=204)

    middleware = RequestIdMiddleware(
        Router(routes=[Route("/test/disconnect", read_request_body, methods=["POST"])])
    )
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/test/disconnect",
        "raw_path": b"/test/disconnect",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"x-request-id", b"req-client-disconnect")],
        "client": ("127.0.0.1", 12345),
        "server": ("test", 80),
    }
    messages: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        messages.append(message)

    with pytest.raises(ClientDisconnect):
        await middleware(scope, receive, send)

    assert messages == []
    assert "unhandled_request_error" not in caplog.text


@pytest.mark.asyncio
async def test_request_id_middleware_preserves_http_exception_semantics() -> None:
    from app.main import create_app

    test_app: FastAPI = create_app()

    @test_app.get("/test/teapot")
    async def raise_http_exception() -> None:
        raise HTTPException(
            status_code=418,
            detail="still a teapot",
            headers={"X-Teapot": "short-and-stout"},
        )

    transport = httpx.ASGITransport(app=test_app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/test/teapot",
            headers={"X-Request-ID": "req-http-exception"},
        )

    assert response.status_code == 418
    assert response.headers["X-Request-ID"] == "req-http-exception"
    assert response.headers["X-Teapot"] == "short-and-stout"
    assert response.json() == {
        "error": {
            "code": "HTTP_418",
            "message": "请求无法处理。",
            "request_id": "req-http-exception",
            "details": {},
        }
    }
    assert "still a teapot" not in response.text
