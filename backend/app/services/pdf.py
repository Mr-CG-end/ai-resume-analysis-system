from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from collections.abc import Sequence
from io import BytesIO
from pathlib import Path

import pypdf.filters
from pypdf import PdfReader
from pypdf.errors import LimitReachedError, ParseError, PdfReadError

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
from app.domain.pdf import ParsedPdf

DEFAULT_MAX_PDF_BYTES = 10_485_760
DEFAULT_MAX_PDF_PAGES = 30
DEFAULT_MAX_RESUME_CHARS = 100_000
MAX_PDF_CONTENT_BYTES = 50 * 1024 * 1024
MAX_RAW_TEXT_CHARS = 1_000_000

_PYPDF_OUTPUT_LIMITS = (
    "FLATE_MAX_BUFFER_SIZE",
    "JBIG2_MAX_OUTPUT_LENGTH",
    "LZW_MAX_OUTPUT_LENGTH",
    "MAX_ARRAY_BASED_STREAM_OUTPUT_LENGTH",
    "MAX_DECLARED_STREAM_LENGTH",
    "RUN_LENGTH_MAX_OUTPUT_LENGTH",
    "ZLIB_MAX_OUTPUT_LENGTH",
)


def _configure_pypdf_output_limits() -> None:
    for limit_name in _PYPDF_OUTPUT_LIMITS:
        if not hasattr(pypdf.filters, limit_name):
            raise RuntimeError(f"Unsupported pypdf release: missing {limit_name}")
        setattr(pypdf.filters, limit_name, MAX_PDF_CONTENT_BYTES)


_configure_pypdf_output_limits()

_HORIZONTAL_WHITESPACE = re.compile(r"[\t\f\v ]+")
_VALID_TEXT = re.compile(r"[A-Za-z0-9\u3400-\u4dbf\u4e00-\u9fff]")
_PAGE_NUMBER = re.compile(
    r"(?:"
    r"第\s*\d+\s*页(?:\s*[/／]\s*共?\s*\d+\s*页?)?"
    r"|page\s*\d+(?:\s*(?:of|/)\s*\d+)?"
    r"|\d+\s*[/／]\s*\d+"
    r"|(?:[1-9]|[12]\d|30)"
    r")",
    re.IGNORECASE,
)


def _normalize_page(page_text: str) -> list[str]:
    normalized = page_text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    return [_HORIZONTAL_WHITESPACE.sub(" ", line).strip() for line in normalized.split("\n")]


def _boundary_indices(lines: Sequence[str]) -> tuple[list[int], list[int]]:
    populated = [index for index, line in enumerate(lines) if line]
    populated_count = len(populated)
    if populated_count < 3:
        depth = 0
    elif populated_count < 5:
        depth = 1
    else:
        depth = 2
    return populated[:depth], list(reversed(populated[-depth:])) if depth else []


def _page_number_indices(lines: Sequence[str]) -> set[int]:
    populated = [index for index, line in enumerate(lines) if line]
    if not populated:
        return set()
    headers, footers = _boundary_indices(lines)
    candidates = set(headers + footers) if headers or footers else {populated[0], populated[-1]}
    return {index for index in candidates if _is_page_number(lines[index])}


def _is_page_number(line: str) -> bool:
    return _PAGE_NUMBER.fullmatch(line.strip()) is not None


def _collapse_blank_lines(lines: Sequence[str]) -> str:
    output: list[str] = []
    blank_pending = False
    for line in lines:
        if not line:
            if output:
                blank_pending = True
            continue
        if blank_pending:
            output.append("")
            blank_pending = False
        output.append(line)
    return "\n".join(output)


def _repeated_lines(counts: Counter[str], participant_count: int) -> set[str]:
    if participant_count < 2:
        return set()
    threshold = max(2, math.ceil(participant_count * 0.6))
    return {line for line, count in counts.items() if count >= threshold}


def clean_pages(pages: Sequence[str]) -> str:
    """Conservatively normalize pages and remove repeated outer boundary lines."""

    normalized_pages = [_normalize_page(page) for page in pages]
    header_counts = (Counter[str](), Counter[str]())
    footer_counts = (Counter[str](), Counter[str]())
    header_participants = [0, 0]
    footer_participants = [0, 0]
    boundaries: list[tuple[list[int], list[int]]] = []

    for lines in normalized_pages:
        headers, footers = _boundary_indices(lines)
        boundaries.append((headers, footers))
        for depth, index in enumerate(headers):
            header_counts[depth].update([lines[index].casefold()])
            header_participants[depth] += 1
        for depth, index in enumerate(footers):
            footer_counts[depth].update([lines[index].casefold()])
            footer_participants[depth] += 1

    repeated_headers = tuple(
        _repeated_lines(counts, header_participants[depth])
        for depth, counts in enumerate(header_counts)
    )
    repeated_footers = tuple(
        _repeated_lines(counts, footer_participants[depth])
        for depth, counts in enumerate(footer_counts)
    )

    cleaned: list[str] = []
    for lines, (headers, footers) in zip(normalized_pages, boundaries, strict=True):
        removable = _page_number_indices(lines)
        for depth, index in enumerate(headers):
            if lines[index].casefold() in repeated_headers[depth]:
                removable.add(index)
        for depth, index in enumerate(footers):
            if lines[index].casefold() in repeated_footers[depth]:
                removable.add(index)
        page = _collapse_blank_lines(
            [line for index, line in enumerate(lines) if index not in removable]
        )
        if page:
            cleaned.append(page)

    return "\n\n".join(cleaned)


def _processing_limit_error() -> PdfProcessingLimitExceededError:
    return PdfProcessingLimitExceededError(details={"max_bytes": MAX_PDF_CONTENT_BYTES})


def _extract_pages(reader: PdfReader, *, max_pages: int) -> tuple[list[str], int]:
    page_count = len(reader.pages)
    if page_count > max_pages:
        raise PdfPageLimitExceededError(
            details={"max_pages": max_pages, "actual_pages": page_count}
        )

    pages: list[str] = []
    content_bytes = 0
    raw_character_count = 0
    for page in reader.pages:
        contents = page.get_contents()
        if contents is not None:
            content_bytes += len(contents.get_data())
            if content_bytes > MAX_PDF_CONTENT_BYTES:
                raise _processing_limit_error()

        page_text = page.extract_text(
            extraction_mode="layout",
            layout_mode_space_vertically=False,
            layout_mode_strip_rotated=False,
        )
        raw_character_count += len(page_text)
        if raw_character_count > MAX_RAW_TEXT_CHARS:
            raise PdfProcessingLimitExceededError(
                details={
                    "max_chars": MAX_RAW_TEXT_CHARS,
                    "actual_chars": raw_character_count,
                }
            )
        pages.append(page_text)
    return pages, page_count


def parse_pdf(
    pdf_bytes: bytes,
    *,
    filename: str,
    content_type: str,
    max_bytes: int = DEFAULT_MAX_PDF_BYTES,
    max_pages: int = DEFAULT_MAX_PDF_PAGES,
    max_chars: int = DEFAULT_MAX_RESUME_CHARS,
) -> ParsedPdf:
    """Validate and parse an in-memory PDF without persisting its contents."""

    validate_pdf_input(
        pdf_bytes,
        filename=filename,
        content_type=content_type,
        max_bytes=max_bytes,
    )

    try:
        with BytesIO(pdf_bytes) as stream:
            reader: PdfReader | None = None
            try:
                reader = PdfReader(stream, strict=True)
                if reader.is_encrypted:
                    raise PdfEncryptedError()
                pages, page_count = _extract_pages(reader, max_pages=max_pages)
            finally:
                if reader is not None:
                    reader.close()
    except LimitReachedError as error:
        raise _processing_limit_error() from error
    except (ParseError, PdfReadError) as error:
        raise PdfCorruptedError() from error

    cleaned_text = clean_pages(pages)
    if _VALID_TEXT.search(cleaned_text) is None:
        raise PdfNoExtractableTextError()
    character_count = len(cleaned_text)
    if character_count > max_chars:
        raise PdfTextTooLongError(details={"max_chars": max_chars, "actual_chars": character_count})

    return ParsedPdf(
        filename=filename,
        cleaned_text=cleaned_text,
        page_count=page_count,
        character_count=character_count,
        sha256=hashlib.sha256(pdf_bytes).hexdigest(),
    )


def validate_pdf_input(
    pdf_bytes: bytes,
    *,
    filename: str,
    content_type: str,
    max_bytes: int = DEFAULT_MAX_PDF_BYTES,
) -> None:
    """Validate transport-level PDF constraints before a possible cache lookup."""

    actual_bytes = len(pdf_bytes)
    if actual_bytes > max_bytes:
        raise PdfTooLargeError(details={"max_bytes": max_bytes, "actual_bytes": actual_bytes})
    if Path(filename).suffix.lower() != ".pdf":
        raise UnsupportedMediaTypeError()
    normalized_mime = content_type.partition(";")[0].strip().lower()
    if normalized_mime != "application/pdf":
        raise UnsupportedMediaTypeError()
    if not pdf_bytes.startswith(b"%PDF-"):
        raise UnsupportedMediaTypeError()
