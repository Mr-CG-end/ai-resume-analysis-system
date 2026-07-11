from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, StringConstraints, field_validator, model_validator

from app.schemas.resume import ContractModel, ResumeSnapshot

Keyword = Annotated[str, StringConstraints(min_length=1, max_length=100)]
Summary = Annotated[str, StringConstraints(min_length=1, max_length=500)]
EvidenceText = Annotated[str, StringConstraints(min_length=1, max_length=500)]
MatchMethod = Literal["hybrid", "rule_fallback"]
MatchWarning = Literal["ai_matching_fallback"]


class MatchRequest(ContractModel):
    resume_snapshot: ResumeSnapshot
    job_description: str


class ScoreBreakdown(ContractModel):
    skill_match: int = Field(ge=0, le=100)
    experience_relevance: int = Field(ge=0, le=100)
    overall: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def overall_matches_weighted_components(self) -> Self:
        expected = int(
            (
                Decimal("0.6") * Decimal(self.skill_match)
                + Decimal("0.4") * Decimal(self.experience_relevance)
            ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        if self.overall != expected:
            raise ValueError("overall must equal the weighted component scores")
        return self


class MatchEvidence(ContractModel):
    dimension: Literal["experience"]
    text: EvidenceText

    @field_validator("text")
    @classmethod
    def evidence_must_contain_visible_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("evidence must contain visible text")
        return value


class MatchResponse(ContractModel):
    match_id: str = Field(pattern=r"^mat_[0-9a-f-]{36}$")
    resume_id: str = Field(pattern=r"^res_[0-9a-f-]{36}$")
    jd_keywords: list[Keyword] = Field(max_length=50)
    matched_keywords: list[Keyword] = Field(max_length=50)
    missing_keywords: list[Keyword] = Field(max_length=50)
    scores: ScoreBreakdown
    evidence: list[MatchEvidence] = Field(max_length=5)
    summary: Summary
    method: MatchMethod
    warnings: list[MatchWarning] = Field(default_factory=list)
    degraded: bool
    cached: bool

    @field_validator("match_id")
    @classmethod
    def match_id_is_canonical_uuid4(cls, value: str) -> str:
        identifier = value.removeprefix("mat_")
        parsed = UUID(identifier)
        if parsed.version != 4 or identifier != str(parsed):
            raise ValueError("match_id must contain a canonical UUIDv4")
        return value

    @field_validator("resume_id")
    @classmethod
    def resume_id_is_canonical_uuid4(cls, value: str) -> str:
        identifier = value.removeprefix("res_")
        parsed = UUID(identifier)
        if parsed.version != 4 or identifier != str(parsed):
            raise ValueError("resume_id must contain a canonical UUIDv4")
        return value

    @model_validator(mode="after")
    def response_contract_is_consistent(self) -> Self:
        jd, matched, missing = self.jd_keywords, self.matched_keywords, self.missing_keywords
        if any(len(items) != len(set(items)) for items in (jd, matched, missing)):
            raise ValueError("keywords must be unique")
        if set(matched) & set(missing) or set(matched) | set(missing) != set(jd):
            raise ValueError("matched and missing keywords must partition jd keywords")
        fallback_warning = "ai_matching_fallback" in self.warnings
        if self.method == "rule_fallback" and (not self.degraded or not fallback_warning):
            raise ValueError("rule_fallback requires degraded state and fallback warning")
        if self.method == "hybrid" and (self.degraded or fallback_warning):
            raise ValueError("hybrid requires non-degraded state without fallback warning")
        if self.method == "hybrid" and not self.evidence:
            raise ValueError("hybrid requires verified evidence")
        if self.method == "rule_fallback" and self.evidence:
            raise ValueError("rule_fallback must not contain AI evidence")
        return self
