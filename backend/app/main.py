from fastapi import FastAPI

from app.api.routes.health import router as health_router


def create_app() -> FastAPI:
    application = FastAPI(title="Xingshi Resume API")
    application.include_router(health_router, prefix="/api/v1")
    return application


app = create_app()
