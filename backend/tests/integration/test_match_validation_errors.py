import httpx
import pytest
from fastapi import FastAPI

from app.core.error_handlers import register_error_handlers
from app.core.request_id import RequestIdMiddleware
from app.schemas.match import MatchRequest


def _app() -> FastAPI:
    application = FastAPI()
    register_error_handlers(application)
    application.add_middleware(RequestIdMiddleware)

    @application.post("/api/v1/matches")
    async def create_match(payload: MatchRequest) -> None:
        del payload

    @application.post("/other")
    async def other(payload: MatchRequest) -> None:
        del payload

    return application


async def _post(path: str, payload: dict[str, object]) -> httpx.Response:
    transport = httpx.ASGITransport(app=_app(), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(
            path, json=payload, headers={"X-Request-ID": "req-match-validation"}
        )


@pytest.mark.asyncio
async def test_match_snapshot_validation_has_specific_safe_error() -> None:
    private_text = "private resume text"
    response = await _post(
        "/api/v1/matches",
        {
            "resume_snapshot": {"cleaned_text": private_text},
            "job_description": "x",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"] == {
        "code": "INVALID_RESUME_SNAPSHOT",
        "message": "简历快照无效。",
        "request_id": "req-match-validation",
        "details": {},
    }
    assert private_text not in response.text


@pytest.mark.asyncio
async def test_match_snapshot_error_wins_over_other_body_errors() -> None:
    response = await _post(
        "/api/v1/matches", {"resume_snapshot": {}, "job_description": 42, "unexpected": "forbidden"}
    )
    assert response.json()["error"]["code"] == "INVALID_RESUME_SNAPSHOT"


@pytest.mark.asyncio
async def test_other_route_keeps_generic_validation_error() -> None:
    response = await _post("/other", {"resume_snapshot": {}, "job_description": "x"})
    assert response.json()["error"]["code"] == "REQUEST_VALIDATION_ERROR"
