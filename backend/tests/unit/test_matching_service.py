from __future__ import annotations

from app.services.jd import JdKeywords
from app.services.matching import calculate_overall_score, score_deterministic_match


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
