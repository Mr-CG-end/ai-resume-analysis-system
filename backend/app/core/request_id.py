import logging
import re
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
logger = logging.getLogger(__name__)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming_request_id = request.headers.get("X-Request-ID")
        request_id = (
            incoming_request_id
            if incoming_request_id is not None and SAFE_REQUEST_ID.fullmatch(incoming_request_id)
            else str(uuid4())
        )
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        except Exception:
            logger.error(
                "unhandled_request_error request_id=%s method=%s",
                request_id,
                request.method,
            )
            return JSONResponse(
                status_code=500,
                headers={"X-Request-ID": request_id},
                content={
                    "error": {
                        "code": "INTERNAL_SERVER_ERROR",
                        "message": "服务器内部错误，请稍后重试。",
                        "request_id": request_id,
                        "details": {},
                    }
                },
            )
        response.headers["X-Request-ID"] = request_id
        return response
