from typing import Literal

from pydantic import BaseModel


class DependencyStatus(BaseModel):
    ai: Literal["configured", "unavailable"]
    redis: Literal["disabled", "up", "down"]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "unavailable"]
    version: str
    dependencies: DependencyStatus
