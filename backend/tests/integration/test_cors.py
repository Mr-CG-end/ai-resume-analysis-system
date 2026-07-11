import httpx
import pytest
from fastapi import HTTPException

from app.core.config import Settings
from app.main import create_app

ALLOWED_ORIGIN = "http://localhost:5173"
REQUEST_ID = "req-cors-test"


def _test_app():
    application = create_app(Settings(_env_file=None, cors_origins=ALLOWED_ORIGIN))

    @application.get("/_test/success")
    async def success() -> dict[str, bool]:
        return {"ok": True}

    @application.get("/_test/http-error")
    async def http_error() -> None:
        raise HTTPException(status_code=422)

    @application.get("/_test/crash")
    async def crash() -> None:
        raise RuntimeError("test-only failure")

    return application


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "status_code"),
    [
        ("/_test/success", 200),
        ("/_test/http-error", 422),
        ("/_test/missing", 404),
        ("/_test/crash", 500),
    ],
)
async def test_actual_responses_include_cors_and_request_id(
    path: str,
    status_code: int,
) -> None:
    transport = httpx.ASGITransport(app=_test_app(), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            path,
            headers={"Origin": ALLOWED_ORIGIN, "X-Request-ID": REQUEST_ID},
        )

    assert response.status_code == status_code
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert response.headers["access-control-expose-headers"] == "X-Request-ID"
    assert response.headers["x-request-id"] == REQUEST_ID
    assert "access-control-allow-credentials" not in response.headers


@pytest.mark.asyncio
async def test_preflight_uses_explicit_cors_contract() -> None:
    transport = httpx.ASGITransport(app=_test_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/api/v1/resumes",
            headers={
                "Origin": ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type,X-Request-ID",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert set(response.headers["access-control-allow-methods"].split(", ")) == {
        "GET",
        "POST",
        "OPTIONS",
    }
    allowed_headers = response.headers["access-control-allow-headers"].lower()
    assert "content-type" in allowed_headers
    assert "x-request-id" in allowed_headers
    assert "access-control-allow-credentials" not in response.headers


@pytest.mark.asyncio
async def test_unlisted_origin_is_not_granted_access() -> None:
    transport = httpx.ASGITransport(app=_test_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/_test/success",
            headers={"Origin": "https://evil.example"},
        )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
