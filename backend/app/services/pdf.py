from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

import pymupdf

from app.domain.errors import (
    PdfCorruptedError,
    PdfEncryptedError,
    PdfNoExtractableTextError,
    PdfPageLimitExceededError,
    PdfTextTooLongError,
    PdfTooLargeError,
    UnsupportedMediaTypeError,
)
from app.domain.pdf import ParsedPdf

DEFAULT_MAX_PDF_BYTES = 10_485_760
DEFAULT_MAX_PDF_PAGES = 30
DEFAULT_MAX_RESUME_CHARS = 100_000

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


def _boundary_indices(lines: Sequence[str], *, from_start: bool) -> list[int]:
    populated = [index for index, line in enumerate(lines) if line]
    if not from_start:
        populated.reverse()
    return populated[:2]


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


def clean_pages(pages: Sequence[str]) -> str:
    """Conservatively normalize pages and remove repeated outer boundary lines."""

    normalized_pages = [_normalize_page(page) for page in pages]
    header_counts = (Counter[str](), Counter[str]())
    footer_counts = (Counter[str](), Counter[str]())
    boundaries: list[tuple[list[int], list[int]]] = []

    for lines in normalized_pages:
        headers = _boundary_indices(lines, from_start=True)
        footers = _boundary_indices(lines, from_start=False)
        boundaries.append((headers, footers))
        for depth, index in enumerate(headers):
            header_counts[depth].update([lines[index].casefold()])
        for depth, index in enumerate(footers):
            footer_counts[depth].update([lines[index].casefold()])

    repeat_threshold = max(2, (len(normalized_pages) * 3 + 4) // 5)
    repeated_headers = tuple(
        {
            line
            for line, count in counts.items()
            if count >= (repeat_threshold if depth == 0 else max(2, len(normalized_pages)))
        }
        for depth, counts in enumerate(header_counts)
    )
    repeated_footers = tuple(
        {
            line
            for line, count in counts.items()
            if count >= (repeat_threshold if depth == 0 else max(2, len(normalized_pages)))
        }
        for depth, counts in enumerate(footer_counts)
    )

    cleaned: list[str] = []
    for lines, (headers, footers) in zip(normalized_pages, boundaries, strict=True):
        removable: set[int] = set()
        for depth, index in enumerate(headers):
            line = lines[index]
            if line.casefold() in repeated_headers[depth] or _is_page_number(line):
                removable.add(index)
        for depth, index in enumerate(footers):
            line = lines[index]
            if line.casefold() in repeated_footers[depth] or _is_page_number(line):
                removable.add(index)
        page = _collapse_blank_lines(
            [line for index, line in enumerate(lines) if index not in removable]
        )
        if page:
            cleaned.append(page)

    return "\n\n".join(cleaned)


def _has_encryption_dictionary(document: pymupdf.Document) -> bool:
    value_type: str = document.xref_get_key(-1, "Encrypt")[0]  # type: ignore[no-untyped-call]
    return value_type != "null"


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

    raw_max_chars = max(max_chars, 0) * 2
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

    try:
        with pymupdf.open(  # type: ignore[no-untyped-call]
            stream=pdf_bytes, filetype="pdf"
        ) as document:
            if _has_encryption_dictionary(document) or document.needs_pass:
                raise PdfEncryptedError()
            if document.is_repaired:
                raise PdfCorruptedError()

            page_count = document.page_count
            if page_count > max_pages:
                raise PdfPageLimitExceededError(
                    details={"max_pages": max_pages, "actual_pages": page_count}
                )
            pages: list[str] = []
            raw_character_count = 0
            for page in document:
                page_text = page.get_text("text", sort=True)
                raw_character_count += len(page_text)
                if raw_character_count > raw_max_chars:
                    raise PdfTextTooLongError(
                        details={"max_chars": max_chars, "actual_chars": raw_character_count}
                    )
                pages.append(page_text)
    except pymupdf.FileDataError as error:
        raise PdfCorruptedError() from error

    cleaned_text = clean_pages(pages)
    if _VALID_TEXT.search(cleaned_text) is None:
        raise PdfNoExtractableTextError()
    character_count = len(cleaned_text)
    if character_count > max_chars:
        raise PdfTextTooLongError(details={"max_chars": max_chars, "actual_chars": character_count})

    return ParsedPdf(
        cleaned_text=cleaned_text,
        page_count=page_count,
        character_count=character_count,
        sha256=hashlib.sha256(pdf_bytes).hexdigest(),
    )
