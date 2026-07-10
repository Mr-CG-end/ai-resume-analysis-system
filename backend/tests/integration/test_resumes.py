from __future__ import annotations

import logging
from pathlib import Path

import httpx
import pytest

from app.api.routes.resumes import get_profile_extractor
from app.core.config import Settings, get_settings
from app.main import create_app
from app.schemas.ai_profile import AiProfilePayload
from app.services.profile import AiExtractionError

FIXTURES = Path(__file__).parents[1] / "fixtures"
_EDUCATION_LINE = "Example Technical University | BSc Computer Science | 2018-2022"


def _settings(*, configured: bool = True) -> Settings:
    values: dict[str, object] = {"_env_file": None}
    if configured:
        values.update(
            ai_api_key="test-key",
            ai_base_url="https://ai.example.test/v1",
            ai_model="test-model",
        )
    return Settings(**values)


def _payload() -> AiProfilePayload:
    empty = {"value": None, "evidence": None}
    return AiProfilePayload.model_validate(
        {
            "name": {"value": "Demo Candidate", "evidence": "Demo Candidate"},
            "phone": {"value": "13800138000", "evidence": "Phone: 13800138000"},
            "email": {
                "value": "demo@example.com",
                "evidence": "Email: demo@example.com",
            },
            "address": {
                "value": "Example District, Sample City",
                "evidence": "Address: Example District, Sample City",
            },
            "job_intention": {
                "value": "Backend Engineer",
                "evidence": "Target role: Backend Engineer",
            },
            "expected_salary": empty,
            "education": [
                {
                    "school": {
                        "value": "Example Technical University",
                        "evidence": _EDUCATION_LINE,
                    },
                    "degree": {
                        "value": "BSc Computer Science",
                        "evidence": _EDUCATION_LINE,
                    },
                    "major": empty,
                    "start_date": empty,
                    "end_date": empty,
                }
            ],
            "projects": [
                {
                    "name": {
                        "value": "Synthetic Resume Analyzer",
                        "evidence": "Project: Synthetic Resume Analyzer",
                    },
                    "role": empty,
                    "description": empty,
                    "technologies": [
                        {
                            "value": "Python",
                            "evidence": "Skills: Python, FastAPI, PostgreSQL, Redis",
                        }
                    ],
                }
            ],
            "employment_periods": [],
        }
    )


class FakeExtractor:
    def __init__(self, payload: AiProfilePayload | None = None) -> None:
        self.payload = payload or _payload()
        self.calls = 0

    async def extract(self, cleaned_text: str) -> AiProfilePayload:
        assert "Demo Candidate" in cleaned_text
        self.calls += 1
        return self.payload


class FailingExtractor:
    async def extract(self, cleaned_text: str) -> AiProfilePayload:
        del cleaned_text
        raise AiExtractionError("safe expected failure")


async def _post_resume(
    *,
    settings: Settings,
    extractor: object | None = None,
    pdf_bytes: bytes | None = None,
    request_id: str = "req-resume-test",
    filename: str = "candidate.pdf",
) -> tuple[httpx.Response, object]:
    application = create_app()
    application.dependency_overrides[get_settings] = lambda: settings
    if extractor is not None:
        application.dependency_overrides[get_profile_extractor] = lambda: extractor
    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)
    content = pdf_bytes or (FIXTURES / "resume-valid-3-pages.pdf").read_bytes()
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/resumes",
            files={"file": (filename, content, "application/pdf")},
            headers={"X-Request-ID": request_id},
        )
    return response, application


@pytest.mark.asyncio
async def test_public_resume_route_returns_verified_snapshot() -> None:
    extractor = FakeExtractor()

    response, _ = await _post_resume(settings=_settings(), extractor=extractor)

    assert response.status_code == 201
    assert response.headers["X-Request-ID"] == "req-resume-test"
    body = response.json()
    assert body["resume_id"].startswith("res_")
    assert body["document"] == {
        "filename": "candidate.pdf",
        "page_count": 3,
        "character_count": len(body["cleaned_text"]),
    }
    assert body["profile"]["name"] == "Demo Candidate"
    assert body["profile"]["phone"] == "13800138000"
    assert body["profile"]["education"][0]["school"] == "Example Technical University"
    assert body["profile"]["projects"][0]["technologies"] == ["Python"]
    assert body["degraded"] is False
    assert body["cached"] is False
    assert extractor.calls == 1


@pytest.mark.asyncio
async def test_public_resume_route_accepts_filename_longer_than_255_characters() -> None:
    filename = f"{'x' * 300}.pdf"

    response, _ = await _post_resume(
        settings=_settings(),
        extractor=FakeExtractor(),
        filename=filename,
    )

    assert response.status_code == 201
    assert response.json()["document"]["filename"] == filename


@pytest.mark.asyncio
async def test_missing_ai_configuration_returns_rule_fallback() -> None:
    response, _ = await _post_resume(settings=_settings(configured=False))

    assert response.status_code == 201
    body = response.json()
    assert body["profile"]["phone"] == "13800138000"
    assert body["profile"]["email"] == "demo@example.com"
    assert body["profile"]["name"] is None
    assert body["degraded"] is True
    assert body["warnings"][-1] == "ai_extraction_fallback"


@pytest.mark.asyncio
async def test_expected_ai_failure_returns_rule_fallback() -> None:
    response, _ = await _post_resume(settings=_settings(), extractor=FailingExtractor())

    assert response.status_code == 201
    assert response.json()["degraded"] is True
    assert "ai_extraction_fallback" in response.json()["warnings"]


@pytest.mark.asyncio
async def test_pdf_failure_does_not_call_ai() -> None:
    extractor = FakeExtractor()

    response, _ = await _post_resume(
        settings=_settings(),
        extractor=extractor,
        pdf_bytes=b"not-a-pdf",
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"
    assert extractor.calls == 0


@pytest.mark.asyncio
async def test_success_log_contains_metrics_without_resume_or_provider_data(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="app.api.routes.resumes")

    response, _ = await _post_resume(settings=_settings(), extractor=FakeExtractor())

    assert response.status_code == 201
    records = [record for record in caplog.records if record.name == "app.api.routes.resumes"]
    assert len(records) == 1
    record = records[0]
    assert record.event == "resume_analyzed"
    assert record.request_id == "req-resume-test"
    assert record.page_count == 3
    assert record.degraded is False
    serialized = str(record.__dict__)
    for sensitive in (
        "candidate.pdf",
        "Demo Candidate",
        "13800138000",
        "demo@example.com",
        "test-key",
        "Example District",
    ):
        assert sensitive not in serialized
