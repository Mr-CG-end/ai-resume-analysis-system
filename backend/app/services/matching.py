from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal, Protocol

from app.schemas.ai_match import AiExperiencePayload
from app.services.ai_match import AiMatchingError
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
    matched_responsibilities: tuple[str, ...]
    missing_responsibilities: tuple[str, ...]
    skill_score: int
    experience_score: int
    overall_score: int


@dataclass(frozen=True, slots=True)
class MatchAnalysis(DeterministicMatch):
    evidence: tuple[str, ...]
    method: Literal["hybrid", "rule_fallback"]
    warnings: tuple[Literal["ai_matching_fallback"], ...]
    degraded: bool


class ExperienceAnalyzer(Protocol):
    async def analyze(self, job_description: str, cleaned_text: str) -> AiExperiencePayload: ...


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
    matched_responsibilities = tuple(
        responsibility
        for responsibility in keywords.responsibilities
        if responsibility in resume_responsibilities
    )
    missing_responsibilities = tuple(
        responsibility
        for responsibility in keywords.responsibilities
        if responsibility not in resume_responsibilities
    )
    skill_score = calculate_coverage_score(len(matched_keywords), len(keywords.skills))
    experience_score = calculate_coverage_score(
        len(matched_responsibilities),
        len(keywords.responsibilities),
    )
    return DeterministicMatch(
        matched_keywords=matched_keywords,
        missing_keywords=missing_keywords,
        matched_responsibilities=matched_responsibilities,
        missing_responsibilities=missing_responsibilities,
        skill_score=skill_score,
        experience_score=experience_score,
        overall_score=calculate_overall_score(skill_score, experience_score),
    )


def _fallback_analysis(deterministic: DeterministicMatch) -> MatchAnalysis:
    return MatchAnalysis(
        matched_keywords=deterministic.matched_keywords,
        missing_keywords=deterministic.missing_keywords,
        matched_responsibilities=deterministic.matched_responsibilities,
        missing_responsibilities=deterministic.missing_responsibilities,
        skill_score=deterministic.skill_score,
        experience_score=deterministic.experience_score,
        overall_score=deterministic.overall_score,
        evidence=(),
        method="rule_fallback",
        warnings=("ai_matching_fallback",),
        degraded=True,
    )


async def analyze_match(
    *,
    keywords: JdKeywords,
    job_description: str,
    cleaned_text: str,
    analyzer: ExperienceAnalyzer | None,
) -> MatchAnalysis:
    """Combine deterministic skills with verified AI experience evidence."""
    deterministic = score_deterministic_match(keywords, cleaned_text)
    if analyzer is None:
        return _fallback_analysis(deterministic)

    try:
        payload = await analyzer.analyze(job_description, cleaned_text)
    except AiMatchingError:
        return _fallback_analysis(deterministic)

    evidence = tuple(dict.fromkeys(item for item in payload.evidence if item.strip()))
    if not evidence or any(item not in cleaned_text for item in evidence):
        return _fallback_analysis(deterministic)

    experience_score = payload.experience_relevance
    return MatchAnalysis(
        matched_keywords=deterministic.matched_keywords,
        missing_keywords=deterministic.missing_keywords,
        matched_responsibilities=deterministic.matched_responsibilities,
        missing_responsibilities=deterministic.missing_responsibilities,
        skill_score=deterministic.skill_score,
        experience_score=experience_score,
        overall_score=calculate_overall_score(deterministic.skill_score, experience_score),
        evidence=evidence,
        method="hybrid",
        warnings=(),
        degraded=False,
    )
