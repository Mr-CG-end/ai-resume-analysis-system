from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

Month = Annotated[str, StringConstraints(pattern=r"^\d{4}-(?:0[1-9]|1[0-2])$")]
EducationEndDate = Annotated[
    str,
    StringConstraints(pattern=r"^(?:\d{4}-(?:0[1-9]|1[0-2])|present)$"),
]
WarningCode = Literal[
    "name_not_found",
    "phone_not_found",
    "email_not_found",
    "address_not_found",
    "job_intention_not_found",
    "expected_salary_not_found",
    "years_of_experience_uncertain",
    "ai_extraction_fallback",
]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DocumentMetadata(ContractModel):
    filename: str = Field(min_length=1)
    page_count: int = Field(ge=1, le=30)
    character_count: int = Field(ge=1, le=100_000)


class Education(ContractModel):
    school: str | None = None
    degree: str | None = None
    major: str | None = None
    start_date: Month | None = None
    end_date: EducationEndDate | None = None


class Project(ContractModel):
    name: str | None = None
    date_range: str | None = None
    role: str | None = None
    description: str | None = None
    highlights: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)


class CandidateProfile(ContractModel):
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    job_intention: str | None = None
    expected_salary: str | None = None
    years_of_experience: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    education: list[Education] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)


class ResumeSnapshot(ContractModel):
    resume_id: str = Field(pattern=r"^res_[0-9a-f-]{36}$")
    document: DocumentMetadata
    cleaned_text: str = Field(min_length=1, max_length=100_000)
    profile: CandidateProfile
    warnings: list[WarningCode] = Field(default_factory=list)
    degraded: bool
    cached: bool

    @field_validator("resume_id")
    @classmethod
    def resume_id_is_canonical_uuid4(cls, value: str) -> str:
        identifier = value.removeprefix("res_")
        parsed = UUID(identifier)
        if parsed.version != 4 or identifier != str(parsed):
            raise ValueError("resume_id must contain a canonical UUIDv4")
        return value

    @model_validator(mode="after")
    def character_count_matches_cleaned_text(self) -> Self:
        if self.document.character_count != len(self.cleaned_text):
            raise ValueError("document character_count must match cleaned_text length")
        fallback_warning = "ai_extraction_fallback" in self.warnings
        if self.degraded != fallback_warning:
            raise ValueError("degraded state must match the AI fallback warning")
        return self
