from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.services.jd import (
    RESPONSIBILITY_ALIASES,
    SKILL_ALIASES,
    JdKeywords,
    extract_catalog_keywords,
)


@dataclass(frozen=True, slots=True)
class DeterministicMatch:
    matched_keywords: tuple[str, ...]
    missing_keywords: tuple[str, ...]
    skill_score: int
    experience_score: int
    overall_score: int


def _round_score(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def calculate_coverage_score(matched_count: int, total_count: int) -> int:
    """Calculate an integer percentage using decimal half-up rounding."""
    if total_count == 0:
        return 0
    return _round_score(Decimal(matched_count) * Decimal(100) / Decimal(total_count))


def calculate_overall_score(skill_score: int, experience_score: int) -> int:
    """Apply the frozen v1 60/40 weighting using decimal arithmetic."""
    weighted = Decimal(skill_score) * Decimal("0.6") + Decimal(experience_score) * Decimal("0.4")
    return _round_score(weighted)


def score_deterministic_match(
    keywords: JdKeywords,
    cleaned_text: str,
) -> DeterministicMatch:
    """Score only evidence found in cleaned resume text."""
    resume_skills = set(extract_catalog_keywords(cleaned_text, SKILL_ALIASES))
    resume_responsibilities = set(extract_catalog_keywords(cleaned_text, RESPONSIBILITY_ALIASES))
    matched_keywords = tuple(skill for skill in keywords.skills if skill in resume_skills)
    missing_keywords = tuple(skill for skill in keywords.skills if skill not in resume_skills)
    matched_responsibilities = sum(
        responsibility in resume_responsibilities for responsibility in keywords.responsibilities
    )
    skill_score = calculate_coverage_score(len(matched_keywords), len(keywords.skills))
    experience_score = calculate_coverage_score(
        matched_responsibilities,
        len(keywords.responsibilities),
    )
    return DeterministicMatch(
        matched_keywords=matched_keywords,
        missing_keywords=missing_keywords,
        skill_score=skill_score,
        experience_score=experience_score,
        overall_score=calculate_overall_score(skill_score, experience_score),
    )
