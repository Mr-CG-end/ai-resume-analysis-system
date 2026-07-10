from collections.abc import Callable
from dataclasses import asdict

import httpx
import pytest
from fastapi import FastAPI, Request
from starlette.datastructures import UploadFile

from app.api.upload import parse_pdf_upload
from app.core.error_handlers import register_error_handlers
from app.core.request_id import RequestIdMiddleware
from app.domain.pdf import ParsedPdf


def _test_app(parser: Callable[..., ParsedPdf]) -> FastAPI:
    application = FastAPI()
    register_error_handlers(application)
    application.add_middleware(RequestIdMiddleware)

    @application.post("/internal/pdf")
    async def parse_upload(request: Request) -> dict[str, object]:
        parsed = await parse_pdf_upload(request, parser=parser, max_bytes=8)
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
        ([('resume', ('private-name.pdf', b'%PDF-x', 'application/pdf'))], None),
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
    ) -> ParsedPdf:
        observed.update(
            bytes=pdf_bytes,
            filename=filename,
            content_type=content_type,
            max_bytes=max_bytes,
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
        "pdf_bytes": b"%PDF-ok",
    }

    from app.main import create_app

    production_transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(
        transport=production_transport, base_url="http://test"
    ) as client:
        public_response = await client.post(
            "/api/v1/resumes",
            files=[("file", ("sample.pdf", b"%PDF-ok", "application/pdf"))],
        )

    assert public_response.status_code == 404
