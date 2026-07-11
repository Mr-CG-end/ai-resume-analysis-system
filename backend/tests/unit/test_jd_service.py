from __future__ import annotations

import pytest

from app.services.jd import JdValidationError, extract_jd_keywords


def test_rejects_job_description_shorter_than_twenty_characters_after_strip() -> None:
    with pytest.raises(JdValidationError, match="JD_TOO_SHORT") as raised:
        extract_jd_keywords("  Python developer  ")
    assert raised.value.code == "JD_TOO_SHORT"


def test_rejects_normalized_job_description_longer_than_ten_thousand() -> None:
    with pytest.raises(JdValidationError, match="JD_TOO_LONG") as raised:
        extract_jd_keywords("Ｐ" * 10_001)
    assert raised.value.code == "JD_TOO_LONG"


def test_rejects_description_without_known_keywords() -> None:
    with pytest.raises(JdValidationError, match="JD_KEYWORDS_NOT_FOUND"):
        extract_jd_keywords("负责一项尚未归类的专业工作，并按要求交付结果。")


def test_extracts_canonical_keywords_in_first_occurrence_order_and_deduplicates() -> None:
    parsed = extract_jd_keywords(
        "负责后端开发和接口开发，技术栈包括 k8s、TS、NodeJS、Postgres，"
        "并使用 TypeScript 与 Kubernetes 完成部署上线。"
    )
    assert parsed.skills == ("Kubernetes", "TypeScript", "Node.js", "PostgreSQL")
    assert parsed.responsibilities == ("Backend Development", "API Development", "Deployment")


def test_ascii_aliases_require_alphanumeric_boundaries() -> None:
    parsed = extract_jd_keywords(
        "We build reactive interfaces with JavaScript and Django while doing system design work."
    )
    assert parsed.skills == ("JavaScript", "Django")
    assert "React" not in parsed.skills
    assert "Java" not in parsed.skills


def test_nfkc_is_applied_and_internal_whitespace_is_preserved() -> None:
    parsed = extract_jd_keywords("需要 Ｐｙｔｈｏｎ 工程师\n负责系统设计与团队协作。")
    assert parsed.normalized_text == "需要 Python 工程师\n负责系统设计与团队协作。"
    assert parsed.skills == ("Python",)
