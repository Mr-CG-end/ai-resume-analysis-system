from typing import Literal

from pydantic import BaseModel


class DependencyStatus(BaseModel):
    ai: Literal["configured", "unconfigured"]
    redis: Literal["configured", "disabled"]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    dependencies: DependencyStatus
