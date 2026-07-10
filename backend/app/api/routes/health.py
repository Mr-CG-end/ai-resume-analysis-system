from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.health import DependencyStatus, HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        dependencies=DependencyStatus(
            ai="configured" if settings.ai_api_key else "unconfigured",
            redis="configured" if settings.redis_url else "disabled",
        ),
    )
