from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.core.request_id import RequestIdMiddleware


def create_app() -> FastAPI:
    application = FastAPI(title="Xingshi Resume API")
    application.add_middleware(RequestIdMiddleware)
    application.include_router(health_router, prefix="/api/v1")
    return application


app = create_app()
