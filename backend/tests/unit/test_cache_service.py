import json
from uuid import UUID

import pytest

from app.schemas.match import MatchResponse
from app.schemas.resume import ResumeSnapshot
from app.services.cache import (
    CACHE_TTL_SECONDS,
    build_extract_cache_key,
    build_match_cache_key,
    deserialize_match_response,
    deserialize_resume_snapshot,
    resume_snapshot_hash,
    serialize_cache_payload,
    stable_bytes_hash,
    stable_hash,
)


def _snapshot() -> ResumeSnapshot:
    return ResumeSnapshot.model_validate(
        {
            "resume_id": "res_550e8400-e29b-41d4-a716-446655440000",
            "document": {
                "filename": "resume.pdf",
                "page_count": 1,
                "character_count": 17,
            },
            "cleaned_text": "Python FastAPI 经验",
            "profile": {
                "name": "张三",
                "phone": None,
                "email": None,
                "address": None,
                "job_intention": None,
                "expected_salary": None,
                "years_of_experience": None,
                "education": [],
                "projects": [],
            },
            "warnings": ["phone_not_found", "email_not_found"],
            "degraded": False,
            "cached": False,
        }
    )


def _match_response() -> MatchResponse:
    return MatchResponse.model_validate(
        {
            "match_id": "mat_550e8400-e29b-41d4-a716-446655440000",
            "resume_id": "res_550e8400-e29b-41d4-a716-446655440000",
            "jd_keywords": ["Python"],
            "matched_keywords": ["Python"],
            "missing_keywords": [],
            "scores": {"skill_match": 100, "experience_relevance": 80, "overall": 92},
            "evidence": [{"dimension": "experience", "text": "Python FastAPI 经验"}],
            "summary": "技能匹配，经验相关。",
            "method": "hybrid",
            "warnings": [],
            "degraded": False,
            "cached": False,
        }
    )


def test_stable_hash_uses_exact_utf8_text() -> None:
    assert stable_hash("简历\nPython") == stable_hash("简历\nPython")
    assert stable_hash("简历\nPython") != stable_hash("简历 Python")
    assert len(stable_hash("简历\nPython")) == 64
    assert stable_bytes_hash(b"pdf") != stable_bytes_hash(b"PDF")


def test_resume_hash_excludes_request_level_metadata() -> None:
    first = _snapshot()
    changed = first.model_copy(
        update={
            "resume_id": "res_123e4567-e89b-42d3-a456-426614174000",
            "cached": True,
            "document": first.document.model_copy(update={"filename": "renamed.pdf"}),
        }
    )
    assert resume_snapshot_hash(first) == resume_snapshot_hash(changed)


def test_versioned_cache_keys_follow_documented_format() -> None:
    pdf_hash = stable_hash("pdf bytes")
    resume_hash = stable_hash("resume")
    jd_hash = stable_hash("job description")

    assert build_extract_cache_key(pdf_hash) == f"extract:{pdf_hash}:pdf-v1-profile-v4"
    assert build_extract_cache_key(pdf_hash, "profile-v2") == (f"extract:{pdf_hash}:profile-v2")
    assert build_match_cache_key(resume_hash, jd_hash) == (
        f"match:{resume_hash}:{jd_hash}:score-v1-match-v2"
    )


@pytest.mark.parametrize(
    ("builder", "arguments"),
    [
        (build_extract_cache_key, ("ABC",)),
        (build_extract_cache_key, ("a" * 64, "bad:version")),
        (build_match_cache_key, ("a" * 63, "b" * 64)),
        (build_match_cache_key, ("a" * 64, "b" * 64, "")),
    ],
)
def test_cache_keys_reject_ambiguous_components(
    builder: object,
    arguments: tuple[str, ...],
) -> None:
    with pytest.raises(ValueError):
        builder(*arguments)  # type: ignore[operator]


@pytest.mark.parametrize("model", [_snapshot(), _match_response()])
def test_cache_payload_round_trip_is_stable(model: ResumeSnapshot | MatchResponse) -> None:
    serialized = serialize_cache_payload(model)
    assert serialized == serialize_cache_payload(model)
    assert ": " not in serialized
    assert ", " not in serialized

    if isinstance(model, ResumeSnapshot):
        restored = deserialize_resume_snapshot(serialized)
    else:
        restored = deserialize_match_response(serialized.encode("utf-8"))

    assert restored == model


@pytest.mark.parametrize(
    "payload",
    [
        "not-json",
        "[]",
        json.dumps({"unexpected": "field"}),
        b"\xff",
    ],
)
def test_corrupt_or_wrong_cache_payload_is_a_miss(payload: str | bytes) -> None:
    assert deserialize_resume_snapshot(payload) is None
    assert deserialize_match_response(payload) is None


def test_cache_payload_rejects_extra_fields_and_wrong_scalar_types() -> None:
    snapshot_payload = _snapshot().model_dump(mode="json")
    snapshot_payload["unexpected"] = True
    assert deserialize_resume_snapshot(json.dumps(snapshot_payload)) is None

    match_payload = _match_response().model_dump(mode="json")
    match_payload["scores"]["skill_match"] = "100"
    assert deserialize_match_response(json.dumps(match_payload)) is None


def test_cache_contract_uses_24_hour_ttl() -> None:
    assert CACHE_TTL_SECONDS == 86_400


def test_fixture_ids_remain_uuid4() -> None:
    assert UUID(_snapshot().resume_id.removeprefix("res_")).version == 4
