import re
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming_request_id = request.headers.get("X-Request-ID")
        request_id = (
            incoming_request_id
            if incoming_request_id is not None and SAFE_REQUEST_ID.fullmatch(incoming_request_id)
            else str(uuid4())
        )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
