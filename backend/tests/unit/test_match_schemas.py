from uuid import UUID

import pytest
from pydantic import ValidationError

from app.schemas.match import MatchRequest, MatchResponse


def _snapshot() -> dict[str, object]:
    text = "Python FastAPI 项目经验"
    return {
        "resume_id": "res_550e8400-e29b-41d4-a716-446655440000",
        "document": {"filename": "candidate.pdf", "page_count": 1, "character_count": len(text)},
        "cleaned_text": text,
        "profile": {
            "name": None,
            "phone": None,
            "email": None,
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


def _response(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "match_id": "mat_550e8400-e29b-41d4-a716-446655440001",
        "resume_id": "res_550e8400-e29b-41d4-a716-446655440000",
        "jd_keywords": ["Python", "Redis"],
        "matched_keywords": ["Python"],
        "missing_keywords": ["Redis"],
        "scores": {"skill_match": 50, "experience_relevance": 80, "overall": 62},
        "evidence": [{"dimension": "experience", "text": "FastAPI 项目经验"}],
        "summary": "技能覆盖一般，经历相关性较高。",
        "method": "hybrid",
        "warnings": [],
        "degraded": False,
        "cached": False,
    }
    value.update(changes)
    return value


def test_match_request_reuses_strict_resume_snapshot() -> None:
    request = MatchRequest.model_validate(
        {
            "resume_snapshot": _snapshot(),
            "job_description": "招聘 Python 后端开发工程师，负责接口开发。",
        }
    )
    assert request.resume_snapshot.cleaned_text == "Python FastAPI 项目经验"
    with pytest.raises(ValidationError):
        MatchRequest.model_validate(
            {
                "resume_snapshot": {**_snapshot(), "unexpected": "forbidden"},
                "job_description": "招聘 Python 后端开发工程师，负责接口开发。",
            }
        )


def test_match_response_accepts_canonical_consistent_contract() -> None:
    response = MatchResponse.model_validate(_response())
    assert UUID(response.match_id.removeprefix("mat_")).version == 4
    assert response.scores.overall == 62


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"matched_keywords": ["Python", "Go"]}, "keywords"),
        ({"missing_keywords": ["Python", "Redis"]}, "keywords"),
        ({"scores": {"skill_match": 50, "experience_relevance": 80, "overall": 61}}, "overall"),
        ({"method": "rule_fallback", "degraded": False, "warnings": []}, "rule_fallback"),
        ({"method": "hybrid", "degraded": True, "warnings": ["ai_matching_fallback"]}, "hybrid"),
    ],
)
def test_match_response_rejects_cross_field_contract_violations(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        MatchResponse.model_validate(_response(**changes))


def test_stage_five_allows_valid_cached_response() -> None:
    assert MatchResponse.model_validate(_response(cached=True)).cached is True


@pytest.mark.parametrize(
    "changes",
    [
        {"evidence": []},
        {"evidence": [{"dimension": "experience", "text": " \t"}]},
        {
            "method": "rule_fallback",
            "degraded": True,
            "warnings": ["ai_matching_fallback"],
        },
    ],
)
def test_response_rejects_missing_blank_or_fallback_ai_evidence(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        MatchResponse.model_validate(_response(**changes))


def test_match_response_rejects_noncanonical_id_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        MatchResponse.model_validate(_response(match_id="mat_550E8400-E29B-41D4-A716-446655440001"))
    with pytest.raises(ValidationError):
        MatchResponse.model_validate({**_response(), "provider_payload": {}})
