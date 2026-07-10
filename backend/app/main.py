from fastapi import FastAPI, Request, Response
from starlette.responses import PlainTextResponse

from app.api.routes.health import router as health_router
from app.core.request_id import RequestIdMiddleware


async def unhandled_exception_response(request: Request, _: Exception) -> Response:
    request_id = getattr(request.state, "request_id", None)
    headers = {"X-Request-ID": request_id} if isinstance(request_id, str) else None
    return PlainTextResponse("Internal Server Error", status_code=500, headers=headers)


def create_app() -> FastAPI:
    application = FastAPI(title="Xingshi Resume API")
    application.add_exception_handler(Exception, unhandled_exception_response)
    application.add_middleware(RequestIdMiddleware)
    application.include_router(health_router, prefix="/api/v1")
    return application


app = create_app()
