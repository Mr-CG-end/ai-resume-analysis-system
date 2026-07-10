from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

from app.schemas.ai_profile import (
    AiEducation,
    AiEmploymentPeriod,
    AiProfilePayload,
    AiProject,
    EvidenceValue,
)
from app.schemas.resume import CandidateProfile, Education, Project, WarningCode

_EMAIL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9.!#$%&'*+/=?^_`{|}~-])"
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+"
    r"(?![A-Za-z0-9-])"
)
_PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?86[\s-]?)?1[3-9]\d(?:[\s-]?\d){8}(?!\d)")
_MONTH_PATTERN = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")
_EDUCATION_END_PATTERN = re.compile(r"^(?:\d{4}-(?:0[1-9]|1[0-2])|present)$")

_WARNING_FIELDS: tuple[tuple[str, WarningCode], ...] = (
    ("name", "name_not_found"),
    ("phone", "phone_not_found"),
    ("email", "email_not_found"),
    ("address", "address_not_found"),
    ("job_intention", "job_intention_not_found"),
    ("expected_salary", "expected_salary_not_found"),
    ("years_of_experience", "years_of_experience_uncertain"),
)


class AiExtractionError(Exception):
    """An expected AI extraction failure that can safely use rule fallback."""


class ProfileExtractor(Protocol):
    async def extract(self, cleaned_text: str) -> AiProfilePayload:
        """Extract a schema-constrained profile from cleaned resume text."""


@dataclass(frozen=True, slots=True)
class ProfileAnalysis:
    profile: CandidateProfile
    warnings: tuple[WarningCode, ...]
    degraded: bool


def _normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def _has_exact_evidence(cleaned_text: str, evidence: str) -> bool:
    return evidence in cleaned_text


def _validated_value(
    item: EvidenceValue,
    cleaned_text: str,
    *,
    kind: str = "text",
    pattern: re.Pattern[str] | None = None,
) -> str | None:
    if item.value is None or item.evidence is None:
        return None
    if not _has_exact_evidence(cleaned_text, item.evidence):
        return None

    if kind == "phone":
        value_digits = "".join(character for character in item.value if character.isdigit())
        evidence_digits = "".join(character for character in item.evidence if character.isdigit())
        related = bool(value_digits) and value_digits in evidence_digits
    elif kind == "email":
        related = item.value.casefold() in item.evidence.casefold()
    else:
        related = _normalized(item.value) in _normalized(item.evidence)

    if not related or (pattern is not None and pattern.fullmatch(item.value) is None):
        return None
    return item.value


def _first_phone(cleaned_text: str) -> str | None:
    match = _PHONE_PATTERN.search(cleaned_text)
    if match is None:
        return None
    return match.group(0)


def _first_email(cleaned_text: str) -> str | None:
    match = _EMAIL_PATTERN.search(cleaned_text)
    if match is None:
        return None
    return match.group(0)


def _validated_education(item: AiEducation, cleaned_text: str) -> Education | None:
    education = Education(
        school=_validated_value(item.school, cleaned_text),
        degree=_validated_value(item.degree, cleaned_text),
        major=_validated_value(item.major, cleaned_text),
        start_date=_validated_value(
            item.start_date,
            cleaned_text,
            pattern=_MONTH_PATTERN,
        ),
        end_date=_validated_value(
            item.end_date,
            cleaned_text,
            pattern=_EDUCATION_END_PATTERN,
        ),
    )
    if all(value is None for value in education.model_dump().values()):
        return None
    return education


def _validated_project(item: AiProject, cleaned_text: str) -> Project | None:
    technologies = [
        technology.value
        for technology in item.technologies
        if _has_exact_evidence(cleaned_text, technology.evidence)
        and _normalized(technology.value) in _normalized(technology.evidence)
    ]
    project = Project(
        name=_validated_value(item.name, cleaned_text),
        role=_validated_value(item.role, cleaned_text),
        description=_validated_value(item.description, cleaned_text),
        technologies=technologies,
    )
    if (
        project.name is None
        and project.role is None
        and project.description is None
        and not project.technologies
    ):
        return None
    return project


def _month_number(month: str) -> int:
    year, month_number = month.split("-", maxsplit=1)
    return int(year) * 12 + int(month_number) - 1


def _validated_period(
    period: AiEmploymentPeriod,
    cleaned_text: str,
) -> tuple[int, int] | None:
    if not _has_exact_evidence(cleaned_text, period.start_date.evidence):
        return None
    if not _has_exact_evidence(cleaned_text, period.end_date.evidence):
        return None
    if _normalized(period.start_date.value) not in _normalized(period.start_date.evidence):
        return None
    if _normalized(period.end_date.value) not in _normalized(period.end_date.evidence):
        return None

    start = _month_number(period.start_date.value)
    end = _month_number(period.end_date.value)
    if end < start:
        return None
    return start, end


def _years_of_experience(
    periods: Sequence[AiEmploymentPeriod],
    cleaned_text: str,
) -> float | None:
    valid_periods = [
        interval
        for period in periods
        if (interval := _validated_period(period, cleaned_text)) is not None
    ]
    if not valid_periods:
        return None

    merged: list[list[int]] = []
    for start, end in sorted(valid_periods):
        if merged and start <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    months = sum(end - start + 1 for start, end in merged)
    years = (Decimal(months) / Decimal(12)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return float(years)


def _warnings(profile: CandidateProfile, *, fallback: bool) -> tuple[WarningCode, ...]:
    warnings = tuple(
        warning for field, warning in _WARNING_FIELDS if getattr(profile, field) is None
    )
    if fallback:
        return (*warnings, "ai_extraction_fallback")
    return warnings


def _rule_profile(cleaned_text: str) -> CandidateProfile:
    return CandidateProfile(phone=_first_phone(cleaned_text), email=_first_email(cleaned_text))


def _profile_from_payload(
    payload: AiProfilePayload,
    cleaned_text: str,
) -> CandidateProfile:
    phone = _validated_value(payload.phone, cleaned_text, kind="phone")
    email = _validated_value(payload.email, cleaned_text, kind="email")
    education = [
        education_item
        for item in payload.education
        if (education_item := _validated_education(item, cleaned_text)) is not None
    ]
    projects = [
        project_item
        for item in payload.projects
        if (project_item := _validated_project(item, cleaned_text)) is not None
    ]
    return CandidateProfile(
        name=_validated_value(payload.name, cleaned_text),
        phone=phone or _first_phone(cleaned_text),
        email=email or _first_email(cleaned_text),
        address=_validated_value(payload.address, cleaned_text),
        job_intention=_validated_value(payload.job_intention, cleaned_text),
        expected_salary=_validated_value(payload.expected_salary, cleaned_text),
        years_of_experience=_years_of_experience(payload.employment_periods, cleaned_text),
        education=education,
        projects=projects,
    )


async def analyze_profile(
    cleaned_text: str,
    extractor: ProfileExtractor | None,
) -> ProfileAnalysis:
    if extractor is None:
        profile = _rule_profile(cleaned_text)
        return ProfileAnalysis(
            profile=profile,
            warnings=_warnings(profile, fallback=True),
            degraded=True,
        )

    try:
        payload = await extractor.extract(cleaned_text)
    except AiExtractionError:
        profile = _rule_profile(cleaned_text)
        return ProfileAnalysis(
            profile=profile,
            warnings=_warnings(profile, fallback=True),
            degraded=True,
        )

    profile = _profile_from_payload(payload, cleaned_text)
    return ProfileAnalysis(
        profile=profile,
        warnings=_warnings(profile, fallback=False),
        degraded=False,
    )
