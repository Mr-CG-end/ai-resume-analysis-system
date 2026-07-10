import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import asdict
from typing import BinaryIO

import httpx
import pytest
from fastapi import FastAPI, Request
from starlette.datastructures import Headers, UploadFile
from starlette.requests import ClientDisconnect
from starlette.types import Message

from app.api.upload import parse_pdf_upload
from app.core.error_handlers import register_error_handlers
from app.core.request_id import RequestIdMiddleware
from app.domain.pdf import ParsedPdf


class CountingStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks
        self.yielded = 0

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            self.yielded += 1
            yield chunk


def _test_app(parser: Callable[..., ParsedPdf]) -> FastAPI:
    application = FastAPI()
    register_error_handlers(application)
    application.add_middleware(RequestIdMiddleware)

    @application.post("/internal/pdf")
    async def parse_upload(request: Request) -> dict[str, object]:
        parsed = await parse_pdf_upload(
            request,
            parser=parser,
            max_bytes=8,
            max_pages=3,
            max_chars=100,
        )
        return asdict(parsed)

    return application


async def _post(
    application: FastAPI,
    *,
    files: list[tuple[str, tuple[str, bytes, str]]] | None = None,
    data: dict[str, str] | None = None,
    request_id: str = "req-upload-adapter",
) -> httpx.Response:
    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(
            "/internal/pdf",
            files=files,
            data=data,
            headers={"X-Request-ID": request_id},
        )


def _parsed() -> ParsedPdf:
    return ParsedPdf(
        cleaned_text="safe text",
        page_count=1,
        character_count=9,
        sha256="0" * 64,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("files", "data"),
    [
        (None, None),
        (None, {"file": "not-a-file"}),
        ([("resume", ("private-name.pdf", b"%PDF-x", "application/pdf"))], None),
    ],
)
async def test_missing_or_wrong_file_field_returns_file_required(
    files: list[tuple[str, tuple[str, bytes, str]]] | None,
    data: dict[str, str] | None,
) -> None:
    parser_calls = 0

    def parser(_: bytes, **__: object) -> ParsedPdf:
        nonlocal parser_calls
        parser_calls += 1
        return _parsed()

    response = await _post(_test_app(parser), files=files, data=data)

    assert response.status_code == 400
    assert response.json()["error"] == {
        "code": "FILE_REQUIRED",
        "message": "请上传一个 PDF 文件。",
        "request_id": "req-upload-adapter",
        "details": {},
    }
    assert response.headers["X-Request-ID"] == "req-upload-adapter"
    assert parser_calls == 0
    assert "private-name.pdf" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "files",
    [
        [
            ("file", ("one.pdf", b"%PDF-one", "application/pdf")),
            ("file", ("two.pdf", b"%PDF-two", "application/pdf")),
        ],
        [
            ("file", ("one.pdf", b"%PDF-one", "application/pdf")),
            ("attachment", ("two.pdf", b"%PDF-two", "application/pdf")),
        ],
    ],
)
async def test_repeated_or_additional_file_part_is_rejected_and_all_files_are_closed(
    monkeypatch: pytest.MonkeyPatch,
    files: list[tuple[str, tuple[str, bytes, str]]],
) -> None:
    closed: list[str | None] = []
    original_close = UploadFile.close

    async def recording_close(upload: UploadFile) -> None:
        closed.append(upload.filename)
        await original_close(upload)

    monkeypatch.setattr(UploadFile, "close", recording_close)

    response = await _post(_test_app(lambda *_args, **_kwargs: _parsed()), files=files)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MULTIPLE_FILES_NOT_ALLOWED"
    assert sorted(closed) == ["one.pdf", "two.pdf"]
    assert "one.pdf" not in response.text
    assert "two.pdf" not in response.text


@pytest.mark.asyncio
async def test_adapter_runs_parser_in_worker_thread_at_exact_size_limit() -> None:
    import threading

    caller_thread_id = threading.get_ident()
    observed: dict[str, object] = {}

    def parser(
        pdf_bytes: bytes,
        *,
        filename: str,
        content_type: str,
        max_bytes: int,
        max_pages: int,
        max_chars: int,
    ) -> ParsedPdf:
        observed.update(
            bytes=pdf_bytes,
            filename=filename,
            content_type=content_type,
            max_bytes=max_bytes,
            max_pages=max_pages,
            max_chars=max_chars,
            thread_id=threading.get_ident(),
        )
        return _parsed()

    response = await _post(
        _test_app(parser),
        files=[("file", ("sample.pdf", b"01234567", "application/pdf"))],
    )

    assert response.status_code == 200
    assert observed["bytes"] == b"01234567"
    assert observed["filename"] == "sample.pdf"
    assert observed["content_type"] == "application/pdf"
    assert observed["max_bytes"] == 8
    assert observed["max_pages"] == 3
    assert observed["max_chars"] == 100
    assert observed["thread_id"] != caller_thread_id


@pytest.mark.asyncio
async def test_adapter_rejects_max_plus_one_without_calling_parser() -> None:
    parser_calls = 0

    def parser(_: bytes, **__: object) -> ParsedPdf:
        nonlocal parser_calls
        parser_calls += 1
        return _parsed()

    response = await _post(
        _test_app(parser),
        files=[("file", ("sample.pdf", b"123456789more-data", "application/pdf"))],
    )

    assert response.status_code == 413
    assert response.json()["error"] == {
        "code": "PDF_TOO_LARGE",
        "message": "PDF 文件大小超过限制。",
        "request_id": "req-upload-adapter",
        "details": {"max_bytes": 8, "actual_bytes": 9},
    }
    assert parser_calls == 0


@pytest.mark.asyncio
async def test_content_length_fast_rejection_does_not_consume_request_body() -> None:
    application = _test_app(lambda *_args, **_kwargs: _parsed())
    stream = CountingStream([b"body-must-not-be-read"])
    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/internal/pdf",
            content=stream,
            headers={
                "Content-Type": "multipart/form-data; boundary=x",
                "Content-Length": "100000",
                "X-Request-ID": "req-fast-reject",
            },
        )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PDF_TOO_LARGE"
    assert stream.yielded == 0


@pytest.mark.asyncio
async def test_chunked_oversized_request_stops_consuming_after_total_body_budget() -> None:
    application = _test_app(lambda *_args, **_kwargs: _parsed())
    encoded = httpx.Request(
        "POST",
        "http://test/internal/pdf",
        files=[("file", ("sample.pdf", b"x" * 200_000, "application/pdf"))],
    )
    body = encoded.read()
    chunk_size = 4096
    chunks = [body[index : index + chunk_size] for index in range(0, len(body), chunk_size)]
    stream = CountingStream(chunks)
    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/internal/pdf",
            content=stream,
            headers={
                "Content-Type": encoded.headers["Content-Type"],
                "X-Request-ID": "req-chunked-limit",
            },
        )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PDF_TOO_LARGE"
    assert stream.yielded * chunk_size < len(body)


@pytest.mark.asyncio
async def test_multipart_disconnect_propagates_without_leaking_temporary_files(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import tempfile

    opened: list[tempfile.SpooledTemporaryFile[bytes]] = []
    created_uploads: list[UploadFile] = []
    original_tempfile = tempfile.SpooledTemporaryFile

    def recording_tempfile(*, max_size: int) -> tempfile.SpooledTemporaryFile[bytes]:
        file = original_tempfile(max_size=max_size)
        opened.append(file)
        return file

    class RecordingUploadFile(UploadFile):
        def __init__(
            self,
            file: BinaryIO,
            *,
            size: int | None = None,
            filename: str | None = None,
            headers: Headers | None = None,
        ) -> None:
            super().__init__(file, size=size, filename=filename, headers=headers)
            created_uploads.append(self)

    boundary = b"disconnect-boundary"
    first_chunk = (
        b"--"
        + boundary
        + b'\r\nContent-Disposition: form-data; name="file"; filename="private.pdf"'
        + b"\r\nContent-Type: application/pdf\r\n\r\n"
        + b"x" * (1024 * 1024 + 1)
    )
    messages: list[Message] = [
        {"type": "http.request", "body": first_chunk, "more_body": True},
        {"type": "http.disconnect"},
    ]

    async def receive() -> Message:
        return messages.pop(0)

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/internal/pdf",
            "headers": [
                (
                    b"content-type",
                    b"multipart/form-data; boundary=" + boundary,
                ),
            ],
        },
        receive=receive,
    )
    monkeypatch.setattr("starlette.formparsers.SpooledTemporaryFile", recording_tempfile)
    monkeypatch.setattr("starlette.formparsers.UploadFile", RecordingUploadFile)
    caplog.set_level(logging.ERROR)

    with pytest.raises(ClientDisconnect):
        await parse_pdf_upload(
            request,
            parser=lambda *_args, **_kwargs: _parsed(),
            max_bytes=2 * 1024 * 1024,
        )

    assert all(upload.file.closed for upload in created_uploads)
    assert all(file.closed for file in opened)
    assert not caplog.records


@pytest.mark.asyncio
async def test_three_files_map_parser_limit_to_multiple_files_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tempfile

    opened: list[tempfile.SpooledTemporaryFile[bytes]] = []
    original_tempfile = tempfile.SpooledTemporaryFile

    def recording_tempfile(*, max_size: int) -> tempfile.SpooledTemporaryFile[bytes]:
        file = original_tempfile(max_size=max_size)
        opened.append(file)
        return file

    monkeypatch.setattr("starlette.formparsers.SpooledTemporaryFile", recording_tempfile)
    response = await _post(
        _test_app(lambda *_args, **_kwargs: _parsed()),
        files=[
            ("file", ("one.pdf", b"1", "application/pdf")),
            ("file", ("two.pdf", b"2", "application/pdf")),
            ("file", ("three.pdf", b"3", "application/pdf")),
        ],
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MULTIPLE_FILES_NOT_ALLOWED"
    assert len(opened) == 2
    assert all(file.closed for file in opened)


@pytest.mark.asyncio
async def test_form_parser_field_limit_maps_to_safe_malformed_multipart() -> None:
    response = await _post(
        _test_app(lambda *_args, **_kwargs: _parsed()),
        data={f"field-{index}": "x" for index in range(11)},
        request_id="req-too-many-fields",
    )

    assert response.status_code == 400
    assert response.json()["error"] == {
        "code": "MALFORMED_MULTIPART",
        "message": "上传请求格式无效。",
        "request_id": "req-too-many-fields",
        "details": {},
    }


@pytest.mark.asyncio
async def test_missing_boundary_maps_to_safe_malformed_multipart_without_parser_detail(
    caplog: pytest.LogCaptureFixture,
) -> None:
    application = _test_app(lambda *_args, **_kwargs: _parsed())
    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)
    caplog.set_level(logging.WARNING, logger="app.core.error_handlers")

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/internal/pdf",
            content=b"private-body-content",
            headers={
                "Content-Type": "multipart/form-data",
                "X-Request-ID": "req-malformed-upload",
            },
        )

    assert response.status_code == 400
    assert response.json()["error"] == {
        "code": "MALFORMED_MULTIPART",
        "message": "上传请求格式无效。",
        "request_id": "req-malformed-upload",
        "details": {},
    }
    assert response.headers["X-Request-ID"] == "req-malformed-upload"
    assert "boundary" not in response.text.lower()
    record_data = str(caplog.records[-1].__dict__)
    assert "private-body-content" not in record_data
    assert "boundary" not in record_data.lower()


@pytest.mark.asyncio
async def test_invalid_multipart_body_maps_to_safe_error_without_parser_detail(
    caplog: pytest.LogCaptureFixture,
) -> None:
    application = _test_app(lambda *_args, **_kwargs: _parsed())
    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)
    caplog.set_level(logging.WARNING, logger="app.core.error_handlers")

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/internal/pdf",
            content=b"private-malformed-body",
            headers={
                "Content-Type": "multipart/form-data; boundary=x",
                "X-Request-ID": "req-invalid-multipart-body",
            },
        )

    assert response.status_code == 400
    assert response.json()["error"] == {
        "code": "MALFORMED_MULTIPART",
        "message": "上传请求格式无效。",
        "request_id": "req-invalid-multipart-body",
        "details": {},
    }
    assert response.headers["X-Request-ID"] == "req-invalid-multipart-body"
    assert "private-malformed-body" not in response.text
    record_data = "\n".join(str(record.__dict__) for record in caplog.records)
    assert "private-malformed-body" not in record_data
    assert "expected boundary" not in record_data.lower()
    assert "boundary character" not in record_data.lower()


@pytest.mark.asyncio
async def test_upload_error_log_does_not_include_filename_or_body(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="app.core.error_handlers")

    response = await _post(
        _test_app(lambda *_args, **_kwargs: _parsed()),
        files=[
            (
                "resume",
                ("private-filename.pdf", b"private-body-content", "application/pdf"),
            )
        ],
        request_id="req-upload-privacy",
    )

    assert response.status_code == 400
    record_data = str(caplog.records[-1].__dict__)
    assert "private-filename.pdf" not in record_data
    assert "private-body-content" not in record_data
    assert caplog.records[-1].request_id == response.headers["X-Request-ID"]


@pytest.mark.asyncio
async def test_upload_file_is_closed_when_parser_returns_expected_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.domain.errors import UnsupportedMediaTypeError

    closed: list[str | None] = []
    original_close = UploadFile.close

    async def recording_close(upload: UploadFile) -> None:
        closed.append(upload.filename)
        await original_close(upload)

    def parser(_: bytes, **__: object) -> ParsedPdf:
        raise UnsupportedMediaTypeError()

    monkeypatch.setattr(UploadFile, "close", recording_close)
    response = await _post(
        _test_app(parser),
        files=[("file", ("sample.pdf", b"not-pdf", "application/pdf"))],
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"
    assert closed == ["sample.pdf"]


@pytest.mark.asyncio
async def test_success_returns_internal_parsed_pdf_without_mounting_public_route() -> None:
    observed: dict[str, object] = {}

    def parser(pdf_bytes: bytes, **metadata: object) -> ParsedPdf:
        observed.update(metadata)
        observed["pdf_bytes"] = pdf_bytes
        return _parsed()

    application = _test_app(parser)
    response = await _post(
        application,
        files=[("file", ("sample.pdf", b"%PDF-ok", "application/pdf"))],
    )

    assert response.status_code == 200
    assert response.json() == asdict(_parsed())
    assert observed == {
        "filename": "sample.pdf",
        "content_type": "application/pdf",
        "max_bytes": 8,
        "max_pages": 3,
        "max_chars": 100,
        "pdf_bytes": b"%PDF-ok",
    }

    from app.main import create_app

    production_transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=production_transport, base_url="http://test") as client:
        public_response = await client.post(
            "/api/v1/resumes",
            files=[("file", ("sample.pdf", b"%PDF-ok", "application/pdf"))],
        )

    assert public_response.status_code == 404
