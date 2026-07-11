from __future__ import annotations

from pathlib import Path

import httpx
import pytest

import app.api.routes.resumes as resume_routes
from app.api.dependencies import get_cache_store
from app.api.routes.matches import get_match_analyzer
from app.api.routes.resumes import get_profile_extractor
from app.core.config import Settings, get_settings
from app.domain.pdf import ParsedPdf
from app.main import create_app
from app.schemas.ai_match import AiExperiencePayload
from app.schemas.ai_profile import AiProfilePayload
from app.services.cache import build_extract_cache_key, stable_bytes_hash

FIXTURES = Path(__file__).parents[1] / "fixtures"


class MemoryCache:
    enabled = True

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.set_calls: list[tuple[str, int]] = []

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, payload: str, *, ttl_seconds: int) -> bool:
        self.values[key] = payload
        self.set_calls.append((key, ttl_seconds))
        return True

    async def aclose(self) -> None:
        return None


class ProfileExtractor:
    def __init__(self) -> None:
        self.calls = 0

    async def extract(self, cleaned_text: str) -> AiProfilePayload:
        self.calls += 1
        assert "Demo Candidate" in cleaned_text
        empty = {"value": None, "evidence": None}
        return AiProfilePayload.model_validate(
            {
                "name": {"value": "Demo Candidate", "evidence": "Demo Candidate"},
                "phone": {"value": "13800138000", "evidence": "Phone: 13800138000"},
                "email": {
                    "value": "demo@example.com",
                    "evidence": "Email: demo@example.com",
                },
                "address": empty,
                "job_intention": empty,
                "expected_salary": empty,
                "education": [],
                "projects": [],
                "employment_periods": [],
            }
        )


class MatchAnalyzer:
    def __init__(self) -> None:
        self.calls = 0

    async def analyze(self, job_description: str, cleaned_text: str) -> AiExperiencePayload:
        self.calls += 1
        assert "Python" in job_description
        evidence = "Skills: Python, FastAPI, PostgreSQL, Redis"
        assert evidence in cleaned_text
        return AiExperiencePayload(experience_relevance=80, evidence=[evidence])


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        ai_api_key="test-key",
        ai_base_url="https://ai.example.test/v1",
        ai_model="test-model",
    )


def _app(cache: MemoryCache, profile: ProfileExtractor, match: MatchAnalyzer) -> object:
    application = create_app()
    application.dependency_overrides[get_settings] = _settings
    application.dependency_overrides[get_cache_store] = lambda: cache
    application.dependency_overrides[get_profile_extractor] = lambda: profile
    application.dependency_overrides[get_match_analyzer] = lambda: match
    return application


@pytest.mark.asyncio
async def test_resume_and_match_second_requests_hit_cache_with_new_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = MemoryCache()
    profile = ProfileExtractor()
    match = MatchAnalyzer()
    transport = httpx.ASGITransport(app=_app(cache, profile, match))
    pdf = (FIXTURES / "resume-valid-3-pages.pdf").read_bytes()
    parse_calls = 0
    original_parse_pdf = resume_routes.parse_pdf

    def counting_parse_pdf(*args: object, **kwargs: object) -> ParsedPdf:
        nonlocal parse_calls
        parse_calls += 1
        return original_parse_pdf(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(resume_routes, "parse_pdf", counting_parse_pdf)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first_resume = await client.post(
            "/api/v1/resumes",
            files={"file": ("first.pdf", pdf, "application/pdf")},
        )
        second_resume = await client.post(
            "/api/v1/resumes",
            files={"file": ("renamed.pdf", pdf, "application/pdf")},
        )

        assert first_resume.status_code == second_resume.status_code == 201
        first_snapshot = first_resume.json()
        second_snapshot = second_resume.json()
        assert first_snapshot["cached"] is False
        assert second_snapshot["cached"] is True
        assert first_snapshot["resume_id"] != second_snapshot["resume_id"]
        assert second_snapshot["document"]["filename"] == "renamed.pdf"
        assert profile.calls == 1
        assert parse_calls == 1

        job_description = "招聘 Python 后端开发工程师，需要 Redis 与 Docker 项目经验。"
        first_match = await client.post(
            "/api/v1/matches",
            json={"resume_snapshot": first_snapshot, "job_description": job_description},
        )
        second_match = await client.post(
            "/api/v1/matches",
            json={"resume_snapshot": second_snapshot, "job_description": job_description},
        )

    assert first_match.status_code == second_match.status_code == 201
    first_result = first_match.json()
    second_result = second_match.json()
    assert first_result["cached"] is False
    assert second_result["cached"] is True
    assert first_result["match_id"] != second_result["match_id"]
    assert second_result["resume_id"] == second_snapshot["resume_id"]
    assert match.calls == 1
    assert len(cache.set_calls) == 2
    assert all(ttl == 86_400 for _, ttl in cache.set_calls)


@pytest.mark.asyncio
async def test_corrupt_cache_payload_is_recomputed_and_overwritten() -> None:
    cache = MemoryCache()
    profile = ProfileExtractor()
    match = MatchAnalyzer()
    transport = httpx.ASGITransport(app=_app(cache, profile, match))
    pdf = (FIXTURES / "resume-valid-3-pages.pdf").read_bytes()
    cache.values[build_extract_cache_key(stable_bytes_hash(pdf))] = "not-json"

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/resumes",
            files={"file": ("candidate.pdf", pdf, "application/pdf")},
        )

    assert response.status_code == 201
    assert response.json()["cached"] is False
    assert profile.calls == 1
