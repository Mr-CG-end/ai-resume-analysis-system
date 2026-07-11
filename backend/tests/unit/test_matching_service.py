from __future__ import annotations

import pytest

from app.schemas.ai_match import AiExperiencePayload
from app.services.ai_match import AiMatchingError
from app.services.jd import JdKeywords
from app.services.matching import analyze_match, calculate_overall_score, score_deterministic_match


class SuccessfulAnalyzer:
    async def analyze(self, job_description: str, cleaned_text: str) -> AiExperiencePayload:
        assert "后端开发" in job_description
        assert "负责后端开发" in cleaned_text
        return AiExperiencePayload(
            experience_relevance=85,
            evidence=["负责后端开发", "负责后端开发"],
        )


class FailingAnalyzer:
    async def analyze(self, job_description: str, cleaned_text: str) -> AiExperiencePayload:
        del job_description, cleaned_text
        raise AiMatchingError("safe failure")


class UnexpectedAnalyzer:
    async def analyze(self, job_description: str, cleaned_text: str) -> AiExperiencePayload:
        del job_description, cleaned_text
        raise RuntimeError("programming error")


def test_matches_only_against_cleaned_text_and_partitions_skills() -> None:
    keywords = JdKeywords(
        skills=("Python", "React", "Docker"), responsibilities=("Backend Development",)
    )
    result = score_deterministic_match(keywords, "使用 Python 与 Docker。负责后端开发和接口维护。")
    assert result.matched_keywords == ("Python", "Docker")
    assert result.missing_keywords == ("React",)
    assert result.skill_score == 67
    assert result.experience_score == 100
    assert result.overall_score == 80


def test_score_uses_half_up_rounding() -> None:
    keywords = JdKeywords(
        skills=("Python", "Java", "React", "Docker", "Redis", "Git", "Linux", "AWS"),
        responsibilities=(),
    )
    result = score_deterministic_match(keywords, "Python Java React Docker Redis")
    assert result.skill_score == 63
    assert result.experience_score == 0
    assert result.overall_score == 38
    assert calculate_overall_score(50, 50) == 50


def test_zero_denominators_score_zero() -> None:
    result = score_deterministic_match(JdKeywords(skills=(), responsibilities=()), "Python")
    assert result.skill_score == 0
    assert result.experience_score == 0
    assert result.overall_score == 0
    assert result.matched_keywords == ()
    assert result.missing_keywords == ()


def test_resume_aliases_use_boundaries_and_canonical_matching() -> None:
    keywords = JdKeywords(
        skills=("Java", "JavaScript", "Kubernetes", "Alibaba Cloud"),
        responsibilities=("Automated Testing", "Performance Optimization"),
    )
    result = score_deterministic_match(
        keywords,
        "JavaScript, k8s 与阿里云；承担自动化测试和性能优化。",
    )
    assert result.matched_keywords == ("JavaScript", "Kubernetes", "Alibaba Cloud")
    assert result.missing_keywords == ("Java",)
    assert result.experience_score == 100


@pytest.mark.asyncio
async def test_valid_ai_result_builds_hybrid_decision() -> None:
    keywords = JdKeywords(skills=("Python", "Redis"), responsibilities=("Backend Development",))
    result = await analyze_match(
        keywords=keywords,
        job_description="招聘 Python 后端开发工程师，需要 Redis 项目经验。",
        cleaned_text="Python 工程师，负责后端开发。",
        analyzer=SuccessfulAnalyzer(),
    )
    assert result.method == "hybrid"
    assert result.degraded is False
    assert result.warnings == ()
    assert result.evidence == ("负责后端开发",)
    assert result.skill_score == 50
    assert result.experience_score == 85
    assert result.overall_score == 64


@pytest.mark.asyncio
@pytest.mark.parametrize("analyzer", [None, FailingAnalyzer()])
async def test_missing_or_expected_ai_failure_uses_rule_fallback(analyzer: object | None) -> None:
    keywords = JdKeywords(skills=("Python",), responsibilities=("Backend Development",))
    result = await analyze_match(
        keywords=keywords,
        job_description="招聘 Python 后端开发工程师，负责稳定交付。",
        cleaned_text="Python 工程师，负责后端开发。",
        analyzer=analyzer,
    )
    assert result.method == "rule_fallback"
    assert result.degraded is True
    assert result.warnings == ("ai_matching_fallback",)
    assert result.evidence == ()
    assert result.experience_score == 100
    assert result.overall_score == 100


@pytest.mark.asyncio
async def test_unexpected_ai_failure_propagates() -> None:
    with pytest.raises(RuntimeError, match="programming error"):
        await analyze_match(
            keywords=JdKeywords(skills=("Python",), responsibilities=()),
            job_description="招聘 Python 工程师，负责业务系统维护工作。",
            cleaned_text="Python",
            analyzer=UnexpectedAnalyzer(),
        )
