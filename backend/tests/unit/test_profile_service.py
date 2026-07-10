from __future__ import annotations

from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from app.schemas.ai_profile import (
    AiEducation,
    AiEmploymentPeriod,
    AiProfilePayload,
    AiProject,
    EvidenceMonth,
    EvidenceText,
    EvidenceValue,
)
from app.services.profile import AiExtractionError, analyze_profile


def evidence(value: str | None = None, source: str | None = None) -> EvidenceValue:
    return EvidenceValue(value=value, evidence=source)


def payload(**overrides: object) -> AiProfilePayload:
    values: dict[str, object] = {
        "name": evidence(),
        "phone": evidence(),
        "email": evidence(),
        "address": evidence(),
        "job_intention": evidence(),
        "expected_salary": evidence(),
        "education": [],
        "projects": [],
        "employment_periods": [],
    }
    values.update(overrides)
    return AiProfilePayload.model_validate(values)


@dataclass
class StubExtractor:
    result: AiProfilePayload

    async def extract(self, cleaned_text: str) -> AiProfilePayload:
        return self.result


class FailingExtractor:
    async def extract(self, cleaned_text: str) -> AiProfilePayload:
        raise AiExtractionError("model unavailable")


class BrokenExtractor:
    async def extract(self, cleaned_text: str) -> AiProfilePayload:
        raise RuntimeError("programming failure")


@pytest.mark.asyncio
async def test_rule_fallback_uses_first_phone_and_email_with_fixed_warning_order() -> None:
    cleaned_text = "联系 13800138000 later 13900139000\nFIRST@Example.com and second@example.com"

    result = await analyze_profile(cleaned_text, None)

    assert result.profile.phone == "13800138000"
    assert result.profile.email == "FIRST@Example.com"
    assert result.profile.education == []
    assert result.profile.projects == []
    assert result.degraded is True
    assert result.warnings == (
        "name_not_found",
        "address_not_found",
        "job_intention_not_found",
        "expected_salary_not_found",
        "years_of_experience_uncertain",
        "ai_extraction_fallback",
    )


@pytest.mark.asyncio
async def test_expected_extraction_failure_uses_same_rule_fallback() -> None:
    result = await analyze_profile("demo@example.com", FailingExtractor())

    assert result.profile.email == "demo@example.com"
    assert result.degraded is True
    assert result.warnings[-1] == "ai_extraction_fallback"


@pytest.mark.asyncio
async def test_unexpected_extractor_failure_is_not_hidden() -> None:
    with pytest.raises(RuntimeError, match="programming failure"):
        await analyze_profile("resume", BrokenExtractor())


@pytest.mark.asyncio
async def test_ai_values_require_exact_evidence_and_normalized_value_relationship() -> None:
    cleaned_text = "候选人：Ａｌｉｃｅ  Ｃｈｅｎ\n现居 Shanghai\n13800138000\ndemo@example.com"
    extracted = payload(
        name=evidence("Alice Chen", "Ａｌｉｃｅ  Ｃｈｅｎ"),
        phone=evidence("13900139000", "联系电话 13900139000"),
        email=evidence("DEMO@EXAMPLE.COM", "demo@example.com"),
        address=evidence("Beijing", "现居 Shanghai"),
        job_intention=evidence("Engineer", "不存在的证据"),
    )

    result = await analyze_profile(cleaned_text, StubExtractor(extracted))

    assert result.profile.name == "Alice Chen"
    assert result.profile.phone == "13800138000"
    assert result.profile.email == "DEMO@EXAMPLE.COM"
    assert result.profile.address is None
    assert result.profile.job_intention is None
    assert result.degraded is False
    assert "address_not_found" in result.warnings
    assert "job_intention_not_found" in result.warnings
    assert "ai_extraction_fallback" not in result.warnings


@pytest.mark.asyncio
async def test_phone_evidence_compares_digits_and_email_compares_casefold() -> None:
    cleaned_text = "电话 +86 138-0013-8000；邮箱 Demo@Example.COM"
    extracted = payload(
        phone=evidence("13800138000", "+86 138-0013-8000"),
        email=evidence("demo@example.com", "Demo@Example.COM"),
    )

    result = await analyze_profile(cleaned_text, StubExtractor(extracted))

    assert result.profile.phone == "13800138000"
    assert result.profile.email == "demo@example.com"


@pytest.mark.asyncio
async def test_invalid_ai_contact_formats_use_rule_values() -> None:
    cleaned_text = "电话 13800138000；邮箱 demo@example.com"
    extracted = payload(
        phone=evidence("1380013800", "13800138000"),
        email=evidence("demo@example", "demo@example.com"),
    )

    result = await analyze_profile(cleaned_text, StubExtractor(extracted))

    assert result.profile.phone == "13800138000"
    assert result.profile.email == "demo@example.com"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value", "source"),
    [
        ("address", "Sample City", "Address: Sample City"),
        ("expected_salary", "20k-30k", "20k-30k/月"),
        ("expected_salary", "20k-30k", "２０ｋ－３０ｋ"),
    ],
    ids=["address-prefix", "truncated-salary", "full-width-salary"],
)
async def test_exact_only_fields_reject_nonidentical_evidence(
    field: str,
    value: str,
    source: str,
) -> None:
    cleaned_text = source
    extracted = payload(**{field: evidence(value, source)})

    result = await analyze_profile(cleaned_text, StubExtractor(extracted))

    assert getattr(result.profile, field) is None


@pytest.mark.asyncio
async def test_education_and_project_fields_are_filtered_independently() -> None:
    cleaned_text = (
        "示例大学 计算机科学 本科 2018-09 2022-06\n简历分析系统 后端开发 使用 FastAPI 和 PostgreSQL"
    )
    extracted = payload(
        education=[
            AiEducation(
                school=evidence("示例大学", "示例大学"),
                degree=evidence("硕士", "本科"),
                major=evidence("计算机科学", "计算机科学"),
                start_date=evidence("2018-09", "2018-09"),
                end_date=evidence("2022-06", "2022-06"),
            ),
            AiEducation(
                school=evidence("虚构大学", "不存在"),
                degree=evidence(),
                major=evidence(),
                start_date=evidence(),
                end_date=evidence(),
            ),
        ],
        projects=[
            AiProject(
                name=evidence("简历分析系统", "简历分析系统"),
                role=evidence("后端开发", "后端开发"),
                description=evidence("生成评分", "使用 FastAPI"),
                technologies=[
                    EvidenceText(value="fastapi", evidence="FastAPI"),
                    EvidenceText(value="Redis", evidence="PostgreSQL"),
                ],
            )
        ],
    )

    result = await analyze_profile(cleaned_text, StubExtractor(extracted))

    assert len(result.profile.education) == 1
    assert result.profile.education[0].model_dump() == {
        "school": "示例大学",
        "degree": None,
        "major": "计算机科学",
        "start_date": "2018-09",
        "end_date": "2022-06",
    }
    assert len(result.profile.projects) == 1
    assert result.profile.projects[0].name == "简历分析系统"
    assert result.profile.projects[0].description is None
    assert result.profile.projects[0].technologies == ["fastapi"]


def period(
    start: str,
    end: str,
    *,
    start_evidence: str | None = None,
    end_evidence: str | None = None,
    interval_evidence: str | None = None,
) -> AiEmploymentPeriod:
    return AiEmploymentPeriod(
        start_date=EvidenceMonth(value=start, evidence=start_evidence or start),
        end_date=EvidenceMonth(value=end, evidence=end_evidence or end),
        evidence=interval_evidence or (start if start == end else f"{start} {end}"),
    )


@pytest.mark.asyncio
async def test_work_periods_merge_overlap_and_adjacency_with_inclusive_endpoints() -> None:
    cleaned_text = "2020-01 2020-06 2020-05 2020-12 2021-01 2022-01"
    extracted = payload(
        employment_periods=[
            period("2020-01", "2020-06"),
            period("2020-05", "2020-12"),
            period("2021-01", "2021-01"),
            period("2022-01", "2022-01"),
        ]
    )

    result = await analyze_profile(cleaned_text, StubExtractor(extracted))

    # 2020-01..2021-01 is 13 months, plus 2022-01: 14 / 12 -> 1.2 HALF_UP.
    assert result.profile.years_of_experience == 1.2
    assert "years_of_experience_uncertain" not in result.warnings


@pytest.mark.asyncio
async def test_reversed_or_unverifiable_periods_are_dropped() -> None:
    cleaned_text = "2023-01 2022-12 2020-01"
    extracted = payload(
        employment_periods=[
            period("2023-01", "2022-12"),
            period("2020-01", "2020-12", end_evidence="不存在"),
        ]
    )

    result = await analyze_profile(cleaned_text, StubExtractor(extracted))

    assert result.profile.years_of_experience is None
    assert "years_of_experience_uncertain" in result.warnings


@pytest.mark.asyncio
async def test_period_rejects_dates_combined_across_noncontiguous_segments() -> None:
    cleaned_text = "2020-01\nCompany A\n2020-12"
    extracted = payload(
        employment_periods=[
            period(
                "2020-01",
                "2020-12",
                interval_evidence="2020-01 2020-12",
            )
        ]
    )

    result = await analyze_profile(cleaned_text, StubExtractor(extracted))

    assert result.profile.years_of_experience is None


@pytest.mark.asyncio
async def test_one_inclusive_month_rounds_half_up_to_one_decimal() -> None:
    extracted = payload(employment_periods=[period("2024-05", "2024-05")])

    result = await analyze_profile("任职 2024-05", StubExtractor(extracted))

    assert result.profile.years_of_experience == 0.1


def test_internal_evidence_strings_are_bounded() -> None:
    assert EvidenceValue(value="x" * 10_000, evidence="x" * 10_000).value is not None

    with pytest.raises(ValidationError):
        EvidenceValue(value="x" * 10_001, evidence="x" * 10_001)


def test_internal_collection_sizes_are_bounded() -> None:
    empty_education = AiEducation(
        school=evidence(),
        degree=evidence(),
        major=evidence(),
        start_date=evidence(),
        end_date=evidence(),
    )
    empty_project = AiProject(
        name=evidence(),
        role=evidence(),
        description=evidence(),
        technologies=[],
    )
    one_period = period("2024-05", "2024-05")

    for field, item in (
        ("education", empty_education),
        ("projects", empty_project),
        ("employment_periods", one_period),
    ):
        with pytest.raises(ValidationError):
            payload(**{field: [item] * 51})

    with pytest.raises(ValidationError):
        AiProject(
            name=evidence(),
            role=evidence(),
            description=evidence(),
            technologies=[EvidenceText(value="Python", evidence="Python")] * 101,
        )
