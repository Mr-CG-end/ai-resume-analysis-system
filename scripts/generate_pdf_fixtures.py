"""Generate the canonical, synthetic PDF fixtures used by backend tests."""

from __future__ import annotations

from pathlib import Path

import pymupdf


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIRECTORY = REPOSITORY_ROOT / "backend" / "tests" / "fixtures"
PAGE = pymupdf.paper_rect("a4")
TEXT_RECT = pymupdf.Rect(64, 72, PAGE.width - 64, PAGE.height - 72)
FIXTURE_PASSWORD = "fixture-password"


def _new_document() -> pymupdf.Document:
    document = pymupdf.open()
    document.set_metadata({})
    return document


def _add_text_page(document: pymupdf.Document, text: str) -> None:
    page = document.new_page(width=PAGE.width, height=PAGE.height)
    remaining = page.insert_textbox(
        TEXT_RECT,
        text,
        fontname="helv",
        fontsize=11,
        lineheight=1.35,
    )
    if remaining < 0:
        raise ValueError("fixture text does not fit on one page")


def _save(document: pymupdf.Document, name: str, **options: object) -> None:
    destination = FIXTURE_DIRECTORY / name
    document.save(destination, garbage=4, clean=True, deflate=True, **options)
    document.close()


def _generate_valid_resume() -> None:
    document = _new_document()
    pages = (
        "PAGE ONE - PROFILE\n"
        "Demo Candidate\n"
        "Phone: 13800138000\n"
        "Email: demo@example.com\n"
        "Address: Example District, Sample City\n"
        "Target role: Backend Engineer",
        "PAGE TWO - EXPERIENCE\n"
        "Example Software Studio | Backend Engineer | 2022-2025\n"
        "Built typed APIs and deterministic document-processing workflows.\n"
        "Skills: Python, FastAPI, PostgreSQL, Redis",
        "PAGE THREE - EDUCATION AND PROJECTS\n"
        "Example Technical University | BSc Computer Science | 2018-2022\n"
        "Project: Synthetic Resume Analyzer\n"
        "All people, organizations, and experience in this fixture are fictional.",
    )
    for text in pages:
        _add_text_page(document, text)
    _save(document, "resume-valid-3-pages.pdf")


def _generate_missing_address_resume() -> None:
    document = _new_document()
    _add_text_page(
        document,
        "MISSING ADDRESS FIXTURE\n"
        "Demo Candidate\n"
        "Phone: 13800138000\n"
        "Email: demo@example.com\n"
        "Skills: Python, FastAPI\n"
        "This synthetic profile intentionally contains no postal address.",
    )
    _save(document, "resume-missing-address.pdf")


def _generate_repeated_header_resume() -> None:
    document = _new_document()
    bodies = (
        "SECTION ONE\nSynthetic profile summary and core skills.",
        "SECTION TWO\nFictional work history and measurable outcomes.",
        "SECTION THREE\nSynthetic education and project details.",
    )
    for page_number, body in enumerate(bodies, start=1):
        _add_text_page(
            document,
            "DEMO CANDIDATE - CONFIDENTIAL TEST FIXTURE\n"
            f"{body}\n"
            "CANONICAL RESUME FIXTURE\n"
            f"Page {page_number} of {len(bodies)}",
        )
    _save(document, "resume-repeated-header.pdf")


def _generate_scan_only_resume() -> None:
    document = _new_document()
    page = document.new_page(width=PAGE.width, height=PAGE.height)
    width, height = 64, 80
    pixels = bytearray()
    for y in range(height):
        for x in range(width):
            shade = 40 if (y // 8) % 2 == 0 and 5 < x < 59 else 235
            pixels.extend((shade, shade, shade))
    image = f"P6\n{width} {height}\n255\n".encode() + bytes(pixels)
    page.insert_image(TEXT_RECT, stream=image)
    _save(document, "resume-scan-only.pdf")


def _generate_encrypted_resume() -> None:
    document = _new_document()
    _add_text_page(document, "ENCRYPTED SYNTHETIC RESUME FIXTURE")
    _save(
        document,
        "resume-encrypted.pdf",
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        owner_pw=FIXTURE_PASSWORD,
        user_pw=FIXTURE_PASSWORD,
        permissions=0,
    )


def _generate_invalid_files() -> None:
    (FIXTURE_DIRECTORY / "resume-corrupted.pdf").write_bytes(
        b"%PDF-1.7\nsynthetic corrupt binary data\x00\xff\x00\n%%EOF\n"
    )
    (FIXTURE_DIRECTORY / "not-a-pdf.pdf").write_bytes(
        b"This is a synthetic non-PDF fixture.\n"
    )


def main() -> None:
    FIXTURE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    _generate_valid_resume()
    _generate_missing_address_resume()
    _generate_repeated_header_resume()
    _generate_scan_only_resume()
    _generate_encrypted_resume()
    _generate_invalid_files()
    print(f"Generated canonical fixtures in {FIXTURE_DIRECTORY}")


if __name__ == "__main__":
    main()
