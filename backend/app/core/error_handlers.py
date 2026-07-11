import logging
from collections.abc import Mapping
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from app.domain.errors import DomainError
from app.schemas.errors import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


def _request_id(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None)
    return request_id if isinstance(request_id, str) else str(uuid4())


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: Mapping[str, object] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    request_id = _request_id(request)
    response_headers = dict(headers or {})
    response_headers["X-Request-ID"] = request_id
    content = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            request_id=request_id,
            details=dict(details or {}),
        )
    )
    logger.warning(
        "expected_request_error",
        extra={
            "event": "expected_request_error",
            "request_id": request_id,
            "method": request.method,
            "status": status_code,
            "code": code,
        },
    )
    return JSONResponse(
        status_code=status_code,
        headers=response_headers,
        content=content.model_dump(mode="json"),
    )


async def domain_error_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, DomainError):
        raise exc
    return _error_response(
        request,
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details,
    )


async def request_validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    invalid_snapshot = request.url.path == "/api/v1/matches" and any(
        tuple(error.get("loc", ()))[:2] == ("body", "resume_snapshot") for error in exc.errors()
    )
    return _error_response(
        request,
        status_code=422,
        code="INVALID_RESUME_SNAPSHOT" if invalid_snapshot else "REQUEST_VALIDATION_ERROR",
        message="简历快照无效。" if invalid_snapshot else "请求参数无效。",
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, HTTPException):
        raise exc
    return _error_response(
        request,
        status_code=exc.status_code,
        code=f"HTTP_{exc.status_code}",
        message="请求无法处理。",
        headers=exc.headers,
    )


def register_error_handlers(application: FastAPI) -> None:
    application.add_exception_handler(DomainError, domain_error_handler)
    application.add_exception_handler(RequestValidationError, request_validation_error_handler)
    application.add_exception_handler(HTTPException, http_exception_handler)
