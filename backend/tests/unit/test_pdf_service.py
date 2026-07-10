from __future__ import annotations

import hashlib
from collections.abc import Iterator

import pymupdf
import pytest

from app.domain.errors import (
    PdfCorruptedError,
    PdfEncryptedError,
    PdfNoExtractableTextError,
    PdfPageLimitExceededError,
    PdfTextTooLongError,
    PdfTooLargeError,
    UnsupportedMediaTypeError,
)
from app.services.pdf import clean_pages, parse_pdf


def make_pdf(pages: list[str], *, encrypted: bool = False) -> bytes:
    document = pymupdf.open()
    for text in pages:
        page = document.new_page()
        if text:
            page.insert_text((72, 72), text)
    options: dict[str, object] = {}
    if encrypted:
        options = {
            "encryption": pymupdf.PDF_ENCRYPT_AES_256,
            "owner_pw": "owner-secret",
            "user_pw": "user-secret",
        }
    try:
        return document.tobytes(**options)
    finally:
        document.close()


@pytest.mark.parametrize(
    ("filename", "content_type", "pdf_bytes"),
    [
        ("resume.txt", "application/pdf", b"%PDF-content"),
        ("resume.pdf", "text/plain", b"%PDF-content"),
        ("resume.pdf", "application/pdf", b"not-a-pdf"),
    ],
)
def test_rejects_any_invalid_type_signal(
    filename: str, content_type: str, pdf_bytes: bytes
) -> None:
    with pytest.raises(UnsupportedMediaTypeError):
        parse_pdf(pdf_bytes, filename=filename, content_type=content_type)


def test_rejects_oversized_bytes_before_opening_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_open(*args: object, **kwargs: object) -> None:
        pytest.fail("oversized input must not reach pymupdf.open")

    monkeypatch.setattr(pymupdf, "open", unexpected_open)
    with pytest.raises(PdfTooLargeError) as captured:
        parse_pdf(
            b"%PDF-" + b"x" * 6,
            filename="resume.pdf",
            content_type="application/pdf",
            max_bytes=10,
        )

    assert captured.value.code == "PDF_TOO_LARGE"
    assert captured.value.details == {"max_bytes": 10, "actual_bytes": 11}


def test_accepts_exact_size_limit() -> None:
    original = make_pdf(["Valid resume text"])
    padded = original + b"\0" * (10_485_760 - len(original))

    result = parse_pdf(
        padded,
        filename="resume.PDF",
        content_type="application/pdf; charset=binary",
    )

    assert result.cleaned_text == "Valid resume text"


def test_extracts_pages_in_order_and_returns_typed_metadata() -> None:
    pdf_bytes = make_pdf(["FIRST 2024", "SECOND Python", "THIRD Redis"])

    result = parse_pdf(pdf_bytes, filename="resume.pdf", content_type="application/pdf")

    assert result.cleaned_text == "FIRST 2024\n\nSECOND Python\n\nTHIRD Redis"
    assert result.page_count == 3
    assert result.character_count == len(result.cleaned_text)
    assert result.sha256 == hashlib.sha256(pdf_bytes).hexdigest()


def test_accepts_thirty_pages_and_rejects_thirty_one() -> None:
    accepted = make_pdf([f"Resume page {index}" for index in range(1, 31)])
    rejected = make_pdf([f"Resume page {index}" for index in range(1, 32)])

    assert (
        parse_pdf(accepted, filename="resume.pdf", content_type="application/pdf").page_count == 30
    )
    with pytest.raises(PdfPageLimitExceededError) as captured:
        parse_pdf(rejected, filename="resume.pdf", content_type="application/pdf")

    assert captured.value.details == {"max_pages": 30, "actual_pages": 31}


def test_rejects_encrypted_pdf() -> None:
    with pytest.raises(PdfEncryptedError):
        parse_pdf(
            make_pdf(["Secret text"], encrypted=True),
            filename="resume.pdf",
            content_type="application/pdf",
        )


@pytest.mark.parametrize("pdf_bytes", [b"%PDF-not-valid", b"%PDF-1.7\ntruncated"])
def test_maps_known_damaged_pdf_to_corrupted(pdf_bytes: bytes) -> None:
    with pytest.raises(PdfCorruptedError):
        parse_pdf(pdf_bytes, filename="resume.pdf", content_type="application/pdf")


@pytest.mark.parametrize("text", ["", " \n\t --- !!! "])
def test_rejects_pdf_without_alphanumeric_or_cjk_text(text: str) -> None:
    with pytest.raises(PdfNoExtractableTextError):
        parse_pdf(make_pdf([text]), filename="resume.pdf", content_type="application/pdf")


def test_rejects_zero_page_pdf_as_having_no_extractable_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class EmptyDocument:
        needs_pass = False
        page_count = 0

        def __enter__(self) -> EmptyDocument:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def __iter__(self) -> Iterator[object]:
            return iter(())

    monkeypatch.setattr(pymupdf, "open", lambda **kwargs: EmptyDocument())

    with pytest.raises(PdfNoExtractableTextError):
        parse_pdf(b"%PDF-placeholder", filename="resume.pdf", content_type="application/pdf")


def test_rejects_cleaned_text_over_limit_without_truncation() -> None:
    with pytest.raises(PdfTextTooLongError) as captured:
        parse_pdf(
            make_pdf(["ABCDEF"]),
            filename="resume.pdf",
            content_type="application/pdf",
            max_chars=5,
        )

    assert captured.value.details == {"max_chars": 5, "actual_chars": 6}


def test_clean_pages_normalizes_whitespace_and_repeated_boundaries() -> None:
    pages = [
        "Company Resume\r\n\r\nAlpha\u00a0  Python\r\nPage 1 of 3",
        "Company Resume\n\nBeta\tRedis\nPage 2 of 3",
        "Company Resume\n\nGamma  SQL\nPage 3 of 3",
    ]

    assert clean_pages(pages) == "Alpha Python\n\nBeta Redis\n\nGamma SQL"


def test_clean_pages_preserves_body_order_and_non_boundary_duplicates() -> None:
    pages = [
        "HEADER\nExperience\nPython\nFOOTER",
        "HEADER\nPython\nEducation\nFOOTER",
        "HEADER\nProjects\nPython\nFOOTER",
    ]

    assert clean_pages(pages) == ("Experience\nPython\n\nPython\nEducation\n\nProjects\nPython")


def test_unknown_extraction_exception_is_not_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    exited = False

    class BrokenPage:
        def get_text(self, *args: object, **kwargs: object) -> str:
            raise RuntimeError("programming failure")

    class BrokenDocument:
        needs_pass = False
        page_count = 1

        def __enter__(self) -> BrokenDocument:
            return self

        def __exit__(self, *args: object) -> None:
            nonlocal exited
            exited = True
            return None

        def __iter__(self) -> Iterator[BrokenPage]:
            yield BrokenPage()

    monkeypatch.setattr(pymupdf, "open", lambda **kwargs: BrokenDocument())

    with pytest.raises(RuntimeError, match="programming failure"):
        parse_pdf(b"%PDF-placeholder", filename="resume.pdf", content_type="application/pdf")

    assert exited is True


def test_extraction_uses_sorted_text(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, bool]] = []

    class TrackingPage:
        def get_text(self, output: str, *, sort: bool) -> str:
            calls.append((output, sort))
            return "Resume text"

    class TrackingDocument:
        needs_pass = False
        page_count = 1

        def __enter__(self) -> TrackingDocument:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def __iter__(self) -> Iterator[TrackingPage]:
            yield TrackingPage()

    monkeypatch.setattr(pymupdf, "open", lambda **kwargs: TrackingDocument())

    parse_pdf(b"%PDF-placeholder", filename="resume.pdf", content_type="application/pdf")

    assert calls == [("text", True)]
