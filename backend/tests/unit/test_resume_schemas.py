from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.schemas.resume import (
    CandidateProfile,
    DocumentMetadata,
    Education,
    Project,
    ResumeSnapshot,
)


def _snapshot_payload() -> dict[str, object]:
    return {
        "resume_id": f"res_{uuid4()}",
        "document": {
            "filename": "resume.pdf",
            "page_count": 3,
            "character_count": 12,
        },
        "cleaned_text": "Candidate CV",
        "profile": {},
        "warnings": [],
        "degraded": False,
        "cached": False,
    }


def test_candidate_profile_serializes_every_field_with_stable_missing_values() -> None:
    serialized = CandidateProfile().model_dump()

    assert serialized == {
        "name": None,
        "phone": None,
        "email": None,
        "address": None,
        "job_intention": None,
        "expected_salary": None,
        "years_of_experience": None,
        "education": [],
        "projects": [],
    }


@pytest.mark.parametrize("field", ["education", "projects"])
def test_candidate_profile_rejects_null_arrays(field: str) -> None:
    with pytest.raises(ValidationError):
        CandidateProfile.model_validate({field: None})


def test_nested_models_keep_stable_fields_and_arrays() -> None:
    assert Education().model_dump() == {
        "school": None,
        "degree": None,
        "major": None,
        "start_date": None,
        "end_date": None,
    }
    assert Project().model_dump() == {
        "name": None,
        "role": None,
        "description": None,
        "technologies": [],
    }

    with pytest.raises(ValidationError):
        Project.model_validate({"technologies": None})


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (
            DocumentMetadata,
            {"filename": "resume.pdf", "page_count": 1, "character_count": 1, "x": 1},
        ),
        (Education, {"x": 1}),
        (Project, {"x": 1}),
        (CandidateProfile, {"x": 1}),
        (ResumeSnapshot, {**_snapshot_payload(), "x": 1}),
    ],
)
def test_contract_models_reject_extra_fields(
    model: type[DocumentMetadata | Education | Project | CandidateProfile | ResumeSnapshot],
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(payload)


@pytest.mark.parametrize("month", ["2024-01", "2024-12"])
def test_education_accepts_valid_month_boundaries(month: str) -> None:
    education = Education(start_date=month, end_date=month)

    assert education.start_date == month
    assert education.end_date == month


def test_education_accepts_present_as_end_date_only() -> None:
    assert Education(end_date="present").end_date == "present"

    with pytest.raises(ValidationError):
        Education(start_date="present")


@pytest.mark.parametrize(
    "month",
    ["2024", "2024-00", "2024-13", "24-01", "2024-1", "2024-01-01", "Present"],
)
def test_education_rejects_invalid_months(month: str) -> None:
    with pytest.raises(ValidationError):
        Education(start_date=month)
    with pytest.raises(ValidationError):
        Education(end_date=month)


@pytest.mark.parametrize(
    ("field", "accepted"),
    [
        ("filename", ["x", "x" * 1_000]),
        ("page_count", [1, 30]),
        ("character_count", [1, 100_000]),
    ],
)
def test_document_metadata_accepts_contract_boundaries(
    field: str, accepted: list[str] | list[int]
) -> None:
    base: dict[str, object] = {
        "filename": "resume.pdf",
        "page_count": 1,
        "character_count": 1,
    }
    for value in accepted:
        DocumentMetadata.model_validate({**base, field: value})


@pytest.mark.parametrize(
    ("field", "rejected"),
    [
        ("filename", [""]),
        ("page_count", [0, 31]),
        ("character_count", [0, 100_001]),
    ],
)
def test_document_metadata_rejects_values_outside_contract(
    field: str, rejected: list[str] | list[int]
) -> None:
    base: dict[str, object] = {
        "filename": "resume.pdf",
        "page_count": 1,
        "character_count": 1,
    }
    for value in rejected:
        with pytest.raises(ValidationError):
            DocumentMetadata.model_validate({**base, field: value})


@pytest.mark.parametrize("years", [0, 0.5, 99.0])
def test_profile_accepts_finite_non_negative_years(years: float) -> None:
    assert CandidateProfile(years_of_experience=years).years_of_experience == years


@pytest.mark.parametrize("years", [-0.1, float("inf"), float("-inf"), float("nan")])
def test_profile_rejects_invalid_years(years: float) -> None:
    with pytest.raises(ValidationError):
        CandidateProfile(years_of_experience=years)


def test_resume_snapshot_accepts_uuid4_and_all_cleaned_text_boundaries() -> None:
    identifier = uuid4()
    payload = _snapshot_payload()
    payload["resume_id"] = f"res_{identifier}"

    for cleaned_text in ["x", "x" * 100_000]:
        document = {**payload["document"], "character_count": len(cleaned_text)}
        snapshot = ResumeSnapshot.model_validate(
            {**payload, "document": document, "cleaned_text": cleaned_text}
        )
        assert UUID(snapshot.resume_id.removeprefix("res_")).version == 4


def test_resume_snapshot_rejects_character_count_mismatch() -> None:
    with pytest.raises(ValidationError, match="character_count"):
        ResumeSnapshot.model_validate(
            {
                **_snapshot_payload(),
                "document": {
                    "filename": "resume.pdf",
                    "page_count": 1,
                    "character_count": 11,
                },
            }
        )


@pytest.mark.parametrize(
    "resume_id",
    [
        str(uuid4()),
        "res_00000000-0000-0000-0000-000000000000",
        "res_550e8400-e29b-11d4-a716-446655440000",
        "res_------------------------------------",
        "res_550E8400-E29B-41D4-A716-446655440000",
    ],
)
def test_resume_snapshot_rejects_non_uuid4_identifiers(resume_id: str) -> None:
    with pytest.raises(ValidationError):
        ResumeSnapshot.model_validate({**_snapshot_payload(), "resume_id": resume_id})


@pytest.mark.parametrize(
    "cleaned_text",
    ["", "x" * 100_001],
    ids=["empty", "over-limit"],
)
def test_resume_snapshot_rejects_cleaned_text_outside_contract(cleaned_text: str) -> None:
    with pytest.raises(ValidationError):
        ResumeSnapshot.model_validate({**_snapshot_payload(), "cleaned_text": cleaned_text})
