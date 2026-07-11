from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.api.routes.health import router as health_router
from app.api.routes.matches import router as matches_router
from app.api.routes.resumes import router as resumes_router
from app.core.config import Settings, get_settings
from app.core.error_handlers import register_error_handlers
from app.core.request_id import RequestIdMiddleware


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    application = FastAPI(title="Xingshi Resume API")
    register_error_handlers(application)
    application.add_middleware(RequestIdMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.allowed_cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    application.include_router(health_router, prefix="/api/v1")
    application.include_router(resumes_router, prefix="/api/v1")
    application.include_router(matches_router, prefix="/api/v1")
    return application


app = create_app()
