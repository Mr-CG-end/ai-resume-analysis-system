from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ParsedPdf:
    """Validated, extracted PDF data without the original file or framework objects."""

    filename: str
    cleaned_text: str
    page_count: int
    character_count: int
    sha256: str
