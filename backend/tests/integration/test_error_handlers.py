import httpx
import pytest
from fastapi import FastAPI, HTTPException, Query

from app.core.error_handlers import register_error_handlers
from app.core.request_id import RequestIdMiddleware
from app.domain.errors import DomainError


class ExpectedFailure(DomainError):
    code = "EXPECTED_FAILURE"
    message = "请求内容不符合要求。"
    status_code = 409


def _test_app() -> FastAPI:
    application = FastAPI()
    register_error_handlers(application)
    application.add_middleware(RequestIdMiddleware)

    @application.get("/domain")
    async def domain_error() -> None:
        raise ExpectedFailure(details={"limit": 3})

    @application.get("/validation")
    async def validation_error(secret: str = Query(min_length=20)) -> None:
        del secret

    @application.get("/http")
    async def http_error() -> None:
        raise HTTPException(
            status_code=418,
            detail="private-detail-must-not-appear",
            headers={"X-Teapot": "short-and-stout"},
        )

    return application


async def _get(path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=_test_app(), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path, headers={"X-Request-ID": "req-errors"})


@pytest.mark.asyncio
async def test_domain_error_uses_safe_unified_contract() -> None:
    response = await _get("/domain")

    assert response.status_code == 409
    assert response.headers["X-Request-ID"] == "req-errors"
    assert response.json() == {
        "error": {
            "code": "EXPECTED_FAILURE",
            "message": "请求内容不符合要求。",
            "request_id": "req-errors",
            "details": {"limit": 3},
        }
    }


@pytest.mark.asyncio
async def test_request_validation_error_does_not_echo_sensitive_input() -> None:
    response = await _get("/validation?secret=private-value")

    assert response.status_code == 422
    assert response.headers["X-Request-ID"] == "req-errors"
    assert response.json()["error"] == {
        "code": "REQUEST_VALIDATION_ERROR",
        "message": "请求参数无效。",
        "request_id": "req-errors",
        "details": {},
    }
    assert "private-value" not in response.text


@pytest.mark.asyncio
async def test_http_exception_uses_status_based_code_and_hides_detail() -> None:
    response = await _get("/http")

    assert response.status_code == 418
    assert response.headers["X-Request-ID"] == "req-errors"
    assert response.headers["X-Teapot"] == "short-and-stout"
    assert response.json()["error"] == {
        "code": "HTTP_418",
        "message": "请求无法处理。",
        "request_id": "req-errors",
        "details": {},
    }
    assert "private-detail-must-not-appear" not in response.text
