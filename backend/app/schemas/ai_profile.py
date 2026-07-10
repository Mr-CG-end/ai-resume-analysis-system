from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from app.schemas.resume import Month

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


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
    technologies: list[EvidenceText]


class AiEmploymentPeriod(AiSchemaModel):
    start_date: EvidenceMonth
    end_date: EvidenceMonth


class AiProfilePayload(AiSchemaModel):
    name: EvidenceValue
    phone: EvidenceValue
    email: EvidenceValue
    address: EvidenceValue
    job_intention: EvidenceValue
    expected_salary: EvidenceValue
    education: list[AiEducation]
    projects: list[AiProject]
    employment_periods: list[AiEmploymentPeriod]
