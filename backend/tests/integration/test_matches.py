from __future__ import annotations

import logging
from uuid import UUID

import httpx
import pytest

from app.api.routes.matches import get_match_analyzer
from app.core.config import Settings, get_settings
from app.main import create_app
from app.schemas.ai_match import AiExperiencePayload
from app.services.ai_match import AiMatchingError

_RESUME_ID = "res_550e8400-e29b-41d4-a716-446655440000"
_CLEANED_TEXT = "Demo Candidate\nPython Redis\n负责后端开发与接口开发\n13800138000 demo@example.com"


def _settings(*, configured: bool) -> Settings:
    values: dict[str, object] = {"_env_file": None}
    if configured:
        values.update(
            ai_api_key="test-key",
            ai_base_url="https://ai.example.test/v1",
            ai_model="test-model",
        )
    return Settings(**values)


def _snapshot() -> dict[str, object]:
    return {
        "resume_id": _RESUME_ID,
        "document": {
            "filename": "candidate.pdf",
            "page_count": 1,
            "character_count": len(_CLEANED_TEXT),
        },
        "cleaned_text": _CLEANED_TEXT,
        "profile": {
            "name": "Demo Candidate",
            "phone": "13800138000",
            "email": "demo@example.com",
            "address": None,
            "job_intention": None,
            "expected_salary": None,
            "years_of_experience": None,
            "education": [],
            "projects": [],
        },
        "warnings": [],
        "degraded": False,
        "cached": False,
    }


class SuccessfulAnalyzer:
    async def analyze(self, job_description: str, cleaned_text: str) -> AiExperiencePayload:
        assert "Python" in job_description
        assert cleaned_text == _CLEANED_TEXT
        return AiExperiencePayload(
            experience_relevance=85,
            evidence=["负责后端开发与接口开发"],
        )


class FailingAnalyzer:
    async def analyze(self, job_description: str, cleaned_text: str) -> AiExperiencePayload:
        del job_description, cleaned_text
        raise AiMatchingError("safe failure")


class UnexpectedAnalyzer:
    async def analyze(self, job_description: str, cleaned_text: str) -> AiExperiencePayload:
        del job_description, cleaned_text
        raise RuntimeError("private programming detail")


async def _post(
    job_description: str,
    *,
    analyzer: object | None,
    configured: bool = True,
) -> httpx.Response:
    application = create_app()
    application.dependency_overrides[get_settings] = lambda: _settings(configured=configured)
    if analyzer is not None:
        application.dependency_overrides[get_match_analyzer] = lambda: analyzer
    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(
            "/api/v1/matches",
            json={"resume_snapshot": _snapshot(), "job_description": job_description},
            headers={"X-Request-ID": "req-match-test"},
        )


@pytest.mark.asyncio
async def test_public_match_route_returns_verified_hybrid_result() -> None:
    response = await _post(
        "招聘 Python 后端开发工程师，需要 Redis 和 Docker 项目经验。",
        analyzer=SuccessfulAnalyzer(),
    )

    assert response.status_code == 201
    assert response.headers["X-Request-ID"] == "req-match-test"
    body = response.json()
    assert UUID(body["match_id"].removeprefix("mat_")).version == 4
    assert body["resume_id"] == _RESUME_ID
    assert body["jd_keywords"] == ["Python", "Redis", "Docker"]
    assert body["matched_keywords"] == ["Python", "Redis"]
    assert body["missing_keywords"] == ["Docker"]
    assert body["scores"] == {
        "skill_match": 67,
        "experience_relevance": 85,
        "overall": 74,
    }
    assert body["evidence"] == [{"dimension": "experience", "text": "负责后端开发与接口开发"}]
    assert body["method"] == "hybrid"
    assert body["warnings"] == []
    assert body["degraded"] is False
    assert body["cached"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("analyzer", "configured"),
    [(None, False), (FailingAnalyzer(), True)],
    ids=["missing-configuration", "expected-ai-failure"],
)
async def test_public_match_route_returns_rule_fallback(
    analyzer: object | None,
    configured: bool,
) -> None:
    response = await _post(
        "招聘 Python 后端开发工程师，负责稳定的业务系统交付。",
        analyzer=analyzer,
        configured=configured,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["method"] == "rule_fallback"
    assert body["degraded"] is True
    assert body["warnings"] == ["ai_matching_fallback"]
    assert body["scores"] == {
        "skill_match": 100,
        "experience_relevance": 100,
        "overall": 100,
    }
    assert body["evidence"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("job_description", "status_code", "code"),
    [
        ("太短", 400, "JD_TOO_SHORT"),
        ("Python" + "x" * 10_001, 400, "JD_TOO_LONG"),
        ("负责优秀业务工作并持续创造高质量客户价值。", 422, "JD_KEYWORDS_NOT_FOUND"),
    ],
)
async def test_public_match_route_maps_jd_errors(
    job_description: str,
    status_code: int,
    code: str,
) -> None:
    response = await _post(job_description, analyzer=SuccessfulAnalyzer())

    assert response.status_code == status_code
    assert response.headers["X-Request-ID"] == "req-match-test"
    assert response.json()["error"]["code"] == code
    assert response.json()["error"]["request_id"] == "req-match-test"


@pytest.mark.asyncio
async def test_match_route_and_response_are_present_in_openapi() -> None:
    application = create_app()
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/openapi.json")

    operation = response.json()["paths"]["/api/v1/matches"]["post"]
    assert operation["responses"]["201"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/MatchResponse"
    )


@pytest.mark.asyncio
async def test_success_log_contains_metrics_without_private_input(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="app.api.routes.matches")

    response = await _post(
        "招聘 Python 后端开发工程师，需要 Redis 和 Docker 项目经验。",
        analyzer=SuccessfulAnalyzer(),
    )

    assert response.status_code == 201
    records = [record for record in caplog.records if record.name == "app.api.routes.matches"]
    assert len(records) == 1
    record = records[0]
    assert record.event == "match_analyzed"
    assert record.request_id == "req-match-test"
    assert record.keyword_count == 3
    assert record.evidence_count == 1
    serialized = str(record.__dict__)
    for sensitive in (
        "candidate.pdf",
        "Demo Candidate",
        "13800138000",
        "demo@example.com",
        "负责后端开发",
        "招聘 Python",
        "test-key",
        _RESUME_ID,
    ):
        assert sensitive not in serialized


@pytest.mark.asyncio
async def test_unexpected_analyzer_error_is_safe_500() -> None:
    response = await _post(
        "招聘 Python 后端开发工程师，负责稳定的业务系统交付。",
        analyzer=UnexpectedAnalyzer(),
    )

    assert response.status_code == 500
    assert "private programming detail" not in response.text
