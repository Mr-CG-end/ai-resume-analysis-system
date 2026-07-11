from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.api.routes.matches import router as matches_router
from app.api.routes.resumes import router as resumes_router
from app.core.error_handlers import register_error_handlers
from app.core.request_id import RequestIdMiddleware


def create_app() -> FastAPI:
    application = FastAPI(title="Xingshi Resume API")
    register_error_handlers(application)
    application.add_middleware(RequestIdMiddleware)
    application.include_router(health_router, prefix="/api/v1")
    application.include_router(resumes_router, prefix="/api/v1")
    application.include_router(matches_router, prefix="/api/v1")
    return application


app = create_app()
