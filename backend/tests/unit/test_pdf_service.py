from __future__ import annotations

import hashlib
from collections.abc import Callable
from io import BytesIO
from types import SimpleNamespace

import pypdf.filters
import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.errors import LimitReachedError, ParseError, PdfReadError
from reportlab.pdfgen import canvas

import app.services.pdf as pdf_service
from app.domain.errors import (
    PdfCorruptedError,
    PdfEncryptedError,
    PdfNoExtractableTextError,
    PdfPageLimitExceededError,
    PdfProcessingLimitExceededError,
    PdfTextTooLongError,
    PdfTooLargeError,
    UnsupportedMediaTypeError,
)
from app.services.pdf import clean_pages, parse_pdf


def make_pdf(pages: list[str], *, encrypted: bool = False, password: str = "secret") -> bytes:
    buffer = BytesIO()
    document = canvas.Canvas(buffer, pageCompression=1)
    for page_text in pages:
        text = document.beginText(72, 760)
        for line in page_text.splitlines() or [""]:
            text.textLine(line)
        document.drawText(text)
        document.showPage()
    document.save()
    pdf_bytes = buffer.getvalue()

    if not encrypted:
        return pdf_bytes

    reader = PdfReader(BytesIO(pdf_bytes), strict=True)
    writer = PdfWriter()
    writer.append_pages_from_reader(reader)
    writer.encrypt(user_password=password, owner_password="owner-secret")
    encrypted_buffer = BytesIO()
    writer.write(encrypted_buffer)
    writer.close()
    return encrypted_buffer.getvalue()


class FakeContents:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def get_data(self) -> bytes:
        return self.data


class FakePage:
    def __init__(
        self,
        text: str,
        *,
        contents: bytes = b"",
        on_extract: Callable[[], None] | None = None,
    ) -> None:
        self.text = text
        self.contents = contents
        self.on_extract = on_extract

    def get_contents(self) -> FakeContents | None:
        return FakeContents(self.contents) if self.contents else None

    def extract_text(self) -> str:
        if self.on_extract is not None:
            self.on_extract()
        return self.text


def install_fake_reader(
    monkeypatch: pytest.MonkeyPatch,
    pages: list[FakePage],
    *,
    encrypted: bool = False,
    on_close: Callable[[], None] | None = None,
) -> None:
    reader = SimpleNamespace(
        is_encrypted=encrypted,
        pages=pages,
        close=on_close or (lambda: None),
    )
    monkeypatch.setattr(pdf_service, "PdfReader", lambda stream, strict: reader)


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
    def unexpected_reader(*args: object, **kwargs: object) -> None:
        pytest.fail("oversized input must not reach PdfReader")

    monkeypatch.setattr(pdf_service, "PdfReader", unexpected_reader)
    with pytest.raises(PdfTooLargeError) as captured:
        parse_pdf(
            b"%PDF-" + b"x" * 6,
            filename="resume.pdf",
            content_type="application/pdf",
            max_bytes=10,
        )

    assert captured.value.details == {"max_bytes": 10, "actual_bytes": 11}


def test_accepts_exact_size_limit() -> None:
    original = make_pdf(["Valid resume text"])
    filename = "resume final.PDF"

    result = parse_pdf(
        original,
        filename=filename,
        content_type="application/pdf; charset=binary",
        max_bytes=len(original),
    )

    assert result.filename == filename
    assert result.cleaned_text == "Valid resume text"


def test_extracts_pages_in_order_and_returns_typed_metadata() -> None:
    pdf_bytes = make_pdf(["FIRST 2024", "SECOND Python", "THIRD Redis"])

    result = parse_pdf(pdf_bytes, filename="resume.pdf", content_type="application/pdf")

    assert result.filename == "resume.pdf"
    assert result.cleaned_text == "FIRST 2024\n\nSECOND Python\n\nTHIRD Redis"
    assert result.page_count == 3
    assert result.character_count == len(result.cleaned_text)
    assert result.sha256 == hashlib.sha256(pdf_bytes).hexdigest()


def test_uses_strict_reader_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: list[bool] = []
    reader = SimpleNamespace(is_encrypted=False, pages=[FakePage("Resume")], close=lambda: None)

    def tracking_reader(stream: BytesIO, strict: bool) -> object:
        observed.append(strict)
        return reader

    monkeypatch.setattr(pdf_service, "PdfReader", tracking_reader)

    parse_pdf(b"%PDF-placeholder", filename="resume.pdf", content_type="application/pdf")

    assert observed == [True]


def test_accepts_thirty_pages_and_rejects_thirty_one() -> None:
    accepted = make_pdf([f"Resume section {index}" for index in range(1, 31)])
    rejected = make_pdf([f"Resume section {index}" for index in range(1, 32)])

    assert (
        parse_pdf(accepted, filename="resume.pdf", content_type="application/pdf").page_count == 30
    )
    with pytest.raises(PdfPageLimitExceededError) as captured:
        parse_pdf(rejected, filename="resume.pdf", content_type="application/pdf")

    assert captured.value.details == {"max_pages": 30, "actual_pages": 31}


@pytest.mark.parametrize("password", ["secret", ""])
def test_rejects_all_encrypted_pdfs(password: str) -> None:
    with pytest.raises(PdfEncryptedError):
        parse_pdf(
            make_pdf(["Secret text"], encrypted=True, password=password),
            filename="resume.pdf",
            content_type="application/pdf",
        )


@pytest.mark.parametrize("error", [PdfReadError("bad xref"), ParseError("bad object")])
def test_maps_known_pypdf_read_errors_to_corrupted(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    def broken_reader(stream: BytesIO, strict: bool) -> None:
        raise error

    monkeypatch.setattr(pdf_service, "PdfReader", broken_reader)

    with pytest.raises(PdfCorruptedError) as captured:
        parse_pdf(b"%PDF-invalid", filename="resume.pdf", content_type="application/pdf")

    assert captured.value.__cause__ is error


def test_maps_pypdf_limit_to_processing_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    error = LimitReachedError("stream limit")

    def limited_reader(stream: BytesIO, strict: bool) -> None:
        raise error

    monkeypatch.setattr(pdf_service, "PdfReader", limited_reader)

    with pytest.raises(PdfProcessingLimitExceededError) as captured:
        parse_pdf(b"%PDF-limited", filename="resume.pdf", content_type="application/pdf")

    assert captured.value.status_code == 422
    assert captured.value.code == "PDF_PROCESSING_LIMIT_EXCEEDED"
    assert captured.value.__cause__ is error


@pytest.mark.parametrize("text", ["", " \n\t --- !!! "])
def test_rejects_pdf_without_alphanumeric_or_cjk_text(text: str) -> None:
    with pytest.raises(PdfNoExtractableTextError):
        parse_pdf(make_pdf([text]), filename="resume.pdf", content_type="application/pdf")


def test_rejects_zero_page_pdf_as_having_no_extractable_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_reader(monkeypatch, [])

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


def test_accepts_raw_text_over_business_limit_when_cleaned_text_fits() -> None:
    pdf_bytes = make_pdf(["Resume\nAlpha\nFooter", "Resume\nGamma\nFooter"])

    result = parse_pdf(
        pdf_bytes,
        filename="resume.pdf",
        content_type="application/pdf",
        max_chars=15,
    )

    assert result.cleaned_text == "Alpha\n\nGamma"
    assert result.character_count == 12


def test_enforces_exact_cumulative_content_stream_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pdf_service, "MAX_PDF_CONTENT_BYTES", 5)
    install_fake_reader(
        monkeypatch,
        [FakePage("Alpha", contents=b"abc"), FakePage("Beta", contents=b"de")],
    )

    result = parse_pdf(b"%PDF-placeholder", filename="resume.pdf", content_type="application/pdf")

    assert result.cleaned_text == "Alpha\n\nBeta"


def test_stops_before_extracting_content_stream_over_cumulative_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extraction_calls = 0

    def extracted() -> None:
        nonlocal extraction_calls
        extraction_calls += 1

    monkeypatch.setattr(pdf_service, "MAX_PDF_CONTENT_BYTES", 5)
    install_fake_reader(
        monkeypatch,
        [
            FakePage("Alpha", contents=b"abc", on_extract=extracted),
            FakePage("Beta", contents=b"def", on_extract=extracted),
        ],
    )

    with pytest.raises(PdfProcessingLimitExceededError):
        parse_pdf(b"%PDF-placeholder", filename="resume.pdf", content_type="application/pdf")

    assert extraction_calls == 1


def test_enforces_exact_raw_character_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pdf_service, "MAX_RAW_TEXT_CHARS", 5)
    install_fake_reader(monkeypatch, [FakePage("abc"), FakePage("de")])

    result = parse_pdf(
        b"%PDF-placeholder",
        filename="resume.pdf",
        content_type="application/pdf",
        max_chars=10,
    )

    assert result.cleaned_text == "abc\n\nde"


def test_stops_when_raw_character_budget_is_exceeded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pdf_service, "MAX_RAW_TEXT_CHARS", 5)
    install_fake_reader(monkeypatch, [FakePage("abc"), FakePage("def")])

    with pytest.raises(PdfProcessingLimitExceededError) as captured:
        parse_pdf(b"%PDF-placeholder", filename="resume.pdf", content_type="application/pdf")

    assert captured.value.details == {"max_chars": 5, "actual_chars": 6}


def test_configures_all_pypdf_stream_output_limits_to_fifty_mib() -> None:
    for limit_name in pdf_service._PYPDF_OUTPUT_LIMITS:
        assert getattr(pypdf.filters, limit_name) == 50 * 1024 * 1024


def test_fails_fast_when_supported_pypdf_limit_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limit_name = pdf_service._PYPDF_OUTPUT_LIMITS[0]
    monkeypatch.delattr(pypdf.filters, limit_name)

    with pytest.raises(RuntimeError, match=limit_name):
        pdf_service._configure_pypdf_output_limits()


def test_maps_real_compressed_stream_limit_to_processing_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_bytes = make_pdf(["A" * 2_000])
    monkeypatch.setattr(pypdf.filters, "ZLIB_MAX_OUTPUT_LENGTH", 64)

    with pytest.raises(PdfProcessingLimitExceededError):
        parse_pdf(pdf_bytes, filename="resume.pdf", content_type="application/pdf")


def test_closes_reader_after_success(monkeypatch: pytest.MonkeyPatch) -> None:
    closed = False

    def mark_closed() -> None:
        nonlocal closed
        closed = True

    install_fake_reader(monkeypatch, [FakePage("Alpha")], on_close=mark_closed)

    parse_pdf(b"%PDF-placeholder", filename="resume.pdf", content_type="application/pdf")

    assert closed is True


def test_closes_reader_when_extraction_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    closed = False

    def mark_closed() -> None:
        nonlocal closed
        closed = True

    def fail_extraction() -> None:
        raise RuntimeError("programming failure")

    install_fake_reader(
        monkeypatch,
        [FakePage("Alpha", on_extract=fail_extraction)],
        on_close=mark_closed,
    )

    with pytest.raises(RuntimeError, match="programming failure"):
        parse_pdf(b"%PDF-placeholder", filename="resume.pdf", content_type="application/pdf")

    assert closed is True


def test_clean_pages_normalizes_whitespace_and_repeated_boundaries() -> None:
    pages = [
        "Company Resume\r\n\r\nAlpha\u00a0  Python\r\nPage 1 of 3",
        "Company Resume\n\nBeta\tRedis\nPage 2 of 3",
        "Company Resume\n\nGamma  SQL\nPage 3 of 3",
    ]

    assert clean_pages(pages) == "Alpha Python\n\nBeta Redis\n\nGamma SQL"


def test_short_pages_do_not_contribute_to_or_lose_repeated_boundaries() -> None:
    pages = [
        "HEADER\nLong body one\nFooter one",
        "HEADER\nLong body two\nFooter two",
        "HEADER\nShort body",
    ]

    assert clean_pages(pages) == (
        "Long body one\nFooter one\n\nLong body two\nFooter two\n\nHEADER\nShort body"
    )


def test_short_pages_still_remove_explicit_page_numbers() -> None:
    pages = ["Page 31 of 99", "Experience\n31 / 99", "1\nEducation"]

    assert clean_pages(pages) == "Experience\n\nEducation"


def test_long_pages_remove_page_numbers_from_second_boundary_lines() -> None:
    pages = [
        "Candidate A\nPage 31 of 99\nExperience\nFooter A\nLegal A",
        "Candidate B\nPage 32 of 99\nEducation\nFooter B\nLegal B",
    ]

    assert clean_pages(pages) == (
        "Candidate A\nExperience\nFooter A\nLegal A\n\nCandidate B\nEducation\nFooter B\nLegal B"
    )


def test_three_and_four_line_pages_check_only_one_line_at_each_end() -> None:
    pages = [
        "HEADER\nKeep second\nBody one\nFOOTER",
        "HEADER\nKeep second\nBody two\nFOOTER",
    ]

    assert clean_pages(pages) == "Keep second\nBody one\n\nKeep second\nBody two"


def test_five_line_pages_check_two_non_overlapping_lines_at_each_end() -> None:
    pages = [
        "HEADER\nCONFIDENTIAL\nAlpha\nCOMPANY\nFOOTER",
        "HEADER\nCONFIDENTIAL\nBeta\nCOMPANY\nFOOTER",
    ]

    assert clean_pages(pages) == "Alpha\n\nBeta"


def test_repeated_line_requires_sixty_percent_of_actual_participants() -> None:
    pages = [
        "HEADER\nAlpha\nFooter A",
        "HEADER\nBeta\nFooter B",
        "Different\nGamma\nFooter C",
    ]

    assert clean_pages(pages) == "Alpha\nFooter A\n\nBeta\nFooter B\n\nDifferent\nGamma\nFooter C"


def test_clean_pages_keeps_header_and_footer_repetition_separate() -> None:
    pages = [
        "Shared line\nFirst body\nUnique footer",
        "Unique header\nSecond body\nShared line",
    ]

    assert clean_pages(pages) == (
        "Shared line\nFirst body\nUnique footer\n\nUnique header\nSecond body\nShared line"
    )


def test_clean_pages_only_removes_conservative_bare_page_numbers() -> None:
    pages = [
        "2024\nExperience\n1",
        "2025\nEducation\n2",
        "13800138000\nProjects\n3",
    ]

    assert clean_pages(pages) == "2024\nExperience\n\n2025\nEducation\n\n13800138000\nProjects"


def test_clean_pages_preserves_bare_numbers_above_page_limit() -> None:
    pages = ["31\nExperience\n30", "99\nEducation\n29"]

    assert clean_pages(pages) == "31\nExperience\n\n99\nEducation"


def test_unknown_exception_propagates_and_input_stream_is_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = BytesIO(b"%PDF-placeholder")

    def tracking_stream(pdf_bytes: bytes) -> BytesIO:
        assert pdf_bytes == b"%PDF-placeholder"
        return stream

    def broken_reader(source: BytesIO, strict: bool) -> None:
        raise RuntimeError("programming failure")

    monkeypatch.setattr(pdf_service, "BytesIO", tracking_stream)
    monkeypatch.setattr(pdf_service, "PdfReader", broken_reader)

    with pytest.raises(RuntimeError, match="programming failure"):
        parse_pdf(b"%PDF-placeholder", filename="resume.pdf", content_type="application/pdf")

    assert stream.closed is True
