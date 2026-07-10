from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.schemas.resume import Month

NonEmptyText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=10_000),
]


class AiSchemaModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceValue(AiSchemaModel):
    value: NonEmptyText | None = None
    evidence: NonEmptyText | None = None

    @model_validator(mode="after")
    def value_and_evidence_are_paired(self) -> Self:
        if (self.value is None) != (self.evidence is None):
            raise ValueError("value and evidence must both be present or both be null")
        return self


class EvidenceText(AiSchemaModel):
    value: NonEmptyText
    evidence: NonEmptyText


class EvidenceMonth(AiSchemaModel):
    value: Month
    evidence: NonEmptyText


class AiEducation(AiSchemaModel):
    school: EvidenceValue
    degree: EvidenceValue
    major: EvidenceValue
    start_date: EvidenceValue
    end_date: EvidenceValue


class AiProject(AiSchemaModel):
    name: EvidenceValue
    role: EvidenceValue
    description: EvidenceValue
    technologies: list[EvidenceText] = Field(max_length=100)


class AiEmploymentPeriod(AiSchemaModel):
    start_date: EvidenceMonth
    end_date: EvidenceMonth
    evidence: NonEmptyText


class AiProfilePayload(AiSchemaModel):
    name: EvidenceValue
    phone: EvidenceValue
    email: EvidenceValue
    address: EvidenceValue
    job_intention: EvidenceValue
    expected_salary: EvidenceValue
    education: list[AiEducation] = Field(max_length=50)
    projects: list[AiProject] = Field(max_length=50)
    employment_periods: list[AiEmploymentPeriod] = Field(max_length=50)
