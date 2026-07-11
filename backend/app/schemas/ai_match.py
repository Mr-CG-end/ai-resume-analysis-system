from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

EvidenceText = Annotated[
    str,
    StringConstraints(strip_whitespace=False, min_length=1, max_length=500),
]


class AiExperiencePayload(BaseModel):
    """Strict internal model output for experience matching."""

    model_config = ConfigDict(extra="forbid")

    experience_relevance: int = Field(ge=0, le=100)
    evidence: list[EvidenceText] = Field(max_length=5)
