from typing import Protocol

from fastapi import Request
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException
from starlette.types import Message

from app.domain.errors import DomainError, PdfTooLargeError
from app.domain.pdf import ParsedPdf
from app.services.pdf import parse_pdf

READ_CHUNK_BYTES = 64 * 1024
MULTIPART_ENVELOPE_BYTES = 64 * 1024
MAX_MULTIPART_FILES = 2
MAX_MULTIPART_FIELDS = 10


class _RequestBodyTooLarge(MultiPartException):
    pass


class _BufferedReceive:
    def __init__(self, body: bytes) -> None:
        self._body = body
        self._sent = False

    async def __call__(self) -> Message:
        if self._sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        self._sent = True
        return {"type": "http.request", "body": self._body, "more_body": False}


class PdfParser(Protocol):
    def __call__(
        self,
        pdf_bytes: bytes,
        *,
        filename: str,
        content_type: str,
        max_bytes: int,
        max_pages: int,
        max_chars: int,
    ) -> ParsedPdf: ...


class FileRequiredError(DomainError):
    code = "FILE_REQUIRED"
    message = "请上传一个 PDF 文件。"
    status_code = 400


class MultipleFilesNotAllowedError(DomainError):
    code = "MULTIPLE_FILES_NOT_ALLOWED"
    message = "每次只能上传一个 PDF 文件。"
    status_code = 400


class MalformedMultipartError(DomainError):
    code = "MALFORMED_MULTIPART"
    message = "上传请求格式无效。"
    status_code = 400


async def _read_at_most(upload: UploadFile, *, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    bytes_read = 0
    read_limit = max_bytes + 1

    while bytes_read < read_limit:
        chunk = await upload.read(min(READ_CHUNK_BYTES, read_limit - bytes_read))
        if not chunk:
            break
        chunks.append(chunk)
        bytes_read += len(chunk)

    return b"".join(chunks)


async def _read_request_body_at_most(request: Request, *, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    bytes_read = 0

    async for chunk in request.stream():
        bytes_read += len(chunk)
        if bytes_read > max_bytes:
            raise _RequestBodyTooLarge("Request body exceeded maximum size.")
        chunks.append(chunk)

    return b"".join(chunks)


async def parse_pdf_upload(
    request: Request,
    *,
    parser: PdfParser = parse_pdf,
    max_bytes: int = 10 * 1024 * 1024,
    max_pages: int = 30,
    max_chars: int = 100_000,
) -> ParsedPdf:
    request_body_limit = max_bytes + MULTIPART_ENVELOPE_BYTES
    content_length = request.headers.get("Content-Length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError:
            declared_length = 0
        if declared_length > request_body_limit:
            raise PdfTooLargeError(details={"max_bytes": max_bytes})

    try:
        request_body = await _read_request_body_at_most(
            request,
            max_bytes=request_body_limit,
        )
        scope = dict(request.scope)
        scope.pop("app", None)
        bounded_request = Request(scope, receive=_BufferedReceive(request_body))
        form_context = bounded_request.form(
            max_files=MAX_MULTIPART_FILES,
            max_fields=MAX_MULTIPART_FIELDS,
            max_part_size=request_body_limit,
        )
        async with form_context as form:
            file_parts = [
                (field_name, value)
                for field_name, value in form.multi_items()
                if isinstance(value, UploadFile)
            ]

            if len(file_parts) > 1:
                raise MultipleFilesNotAllowedError()
            if len(file_parts) != 1 or file_parts[0][0] != "file":
                raise FileRequiredError()

            upload = file_parts[0][1]
            pdf_bytes = await _read_at_most(upload, max_bytes=max_bytes)
            if len(pdf_bytes) > max_bytes:
                raise PdfTooLargeError(
                    details={"max_bytes": max_bytes, "actual_bytes": len(pdf_bytes)},
                )

            return await run_in_threadpool(
                parser,
                pdf_bytes,
                filename=upload.filename or "",
                content_type=upload.content_type or "",
                max_bytes=max_bytes,
                max_pages=max_pages,
                max_chars=max_chars,
            )
    except _RequestBodyTooLarge as exc:
        raise PdfTooLargeError(details={"max_bytes": max_bytes}) from exc
    except MultiPartException as exc:
        if "maximum number of files" in exc.message.lower():
            raise MultipleFilesNotAllowedError() from exc
        raise MalformedMultipartError() from exc
