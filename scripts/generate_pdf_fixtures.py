"""Generate the canonical, synthetic PDF fixtures used by backend tests."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab import rl_config
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIRECTORY = REPOSITORY_ROOT / "backend" / "tests" / "fixtures"
FIXTURE_PASSWORD = "fixture-password"
PAGE_WIDTH, PAGE_HEIGHT = A4
rl_config.useA85 = 0


def _render_text_pages(pages: tuple[str, ...]) -> bytes:
    output = BytesIO()
    document = Canvas(output, pagesize=A4, pageCompression=1, invariant=1)
    document.setAuthor("")
    document.setCreator("")
    document.setKeywords("")
    document.setSubject("")
    document.setTitle("")
    for page_text in pages:
        text = document.beginText(64, PAGE_HEIGHT - 72)
        text.setFont("Helvetica", 11)
        text.setLeading(15)
        for line in page_text.splitlines():
            text.textLine(line)
        document.drawText(text)
        document.showPage()
    document.save()
    return output.getvalue()


def _render_scan_page() -> bytes:
    output = BytesIO()
    document = Canvas(output, pagesize=A4, pageCompression=1, invariant=1)
    width, height = 64, 80
    pixels = bytearray()
    for y in range(height):
        for x in range(width):
            shade = 40 if (y // 8) % 2 == 0 and 5 < x < 59 else 235
            pixels.extend((shade, shade, shade))
    image = BytesIO(f"P6\n{width} {height}\n255\n".encode() + bytes(pixels))
    document.drawImage(
        ImageReader(image),
        64,
        PAGE_HEIGHT - 360,
        width=PAGE_WIDTH - 128,
        height=288,
    )
    document.showPage()
    document.save()
    return output.getvalue()


def _save_pdf(
    source: bytes,
    output_directory: Path,
    name: str,
    *,
    encrypted: bool = False,
) -> None:
    reader = PdfReader(BytesIO(source), strict=True)
    writer = PdfWriter()
    writer.append_pages_from_reader(reader)
    writer.metadata = None
    if encrypted:
        writer.encrypt(
            user_password=FIXTURE_PASSWORD,
            owner_password=FIXTURE_PASSWORD,
            algorithm="RC4-128",
            permissions_flag=0,
        )
    output = BytesIO()
    writer.write(output)
    pdf = output.getvalue()
    xref_start = pdf.rfind(b"\nxref\n") + 1
    trailer_start = pdf.find(b"trailer\n", xref_start)
    if xref_start == 0 or trailer_start < 0:
        raise ValueError("generated fixture has no classic cross-reference table")
    xref = pdf[xref_start:trailer_start]
    clean_xref = xref.replace(b" n \n", b" n\n").replace(b" f \n", b" f\n")
    (output_directory / name).write_bytes(
        pdf[:xref_start] + clean_xref + pdf[trailer_start:]
    )


def _generate_valid_resume(output_directory: Path) -> None:
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
    _save_pdf(_render_text_pages(pages), output_directory, "resume-valid-3-pages.pdf")


def _generate_missing_address_resume(output_directory: Path) -> None:
    pages = (
        "MISSING ADDRESS FIXTURE\n"
        "Demo Candidate\n"
        "Phone: 13800138000\n"
        "Email: demo@example.com\n"
        "Skills: Python, FastAPI\n"
        "This synthetic profile intentionally omits location details.",
    )
    _save_pdf(_render_text_pages(pages), output_directory, "resume-missing-address.pdf")


def _generate_repeated_header_resume(output_directory: Path) -> None:
    bodies = (
        "SECTION ONE\nSynthetic profile summary and core skills.",
        "SECTION TWO\nFictional work history and measurable outcomes.",
        "SECTION THREE\nSynthetic education and project details.",
    )
    pages = tuple(
        (
            "DEMO CANDIDATE - CONFIDENTIAL TEST FIXTURE\n"
            f"{body}\n"
            "CANONICAL RESUME FIXTURE\n"
            f"Page {page_number} of {len(bodies)}"
        )
        for page_number, body in enumerate(bodies, start=1)
    )
    _save_pdf(_render_text_pages(pages), output_directory, "resume-repeated-header.pdf")


def _generate_scan_only_resume(output_directory: Path) -> None:
    _save_pdf(_render_scan_page(), output_directory, "resume-scan-only.pdf")


def _generate_encrypted_resume(output_directory: Path) -> None:
    _save_pdf(
        _render_text_pages(("ENCRYPTED SYNTHETIC RESUME FIXTURE",)),
        output_directory,
        "resume-encrypted.pdf",
        encrypted=True,
    )


def _generate_invalid_files(output_directory: Path) -> None:
    (output_directory / "resume-corrupted.pdf").write_bytes(
        b"%PDF-1.7\nsynthetic corrupt binary data\x00\xff\x00\n%%EOF\n"
    )
    (output_directory / "not-a-pdf.pdf").write_bytes(
        b"This is a synthetic non-PDF fixture.\n"
    )


def generate_fixtures(output_directory: Path = FIXTURE_DIRECTORY) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)
    _generate_valid_resume(output_directory)
    _generate_missing_address_resume(output_directory)
    _generate_repeated_header_resume(output_directory)
    _generate_scan_only_resume(output_directory)
    _generate_encrypted_resume(output_directory)
    _generate_invalid_files(output_directory)


def main() -> None:
    generate_fixtures()
    print(f"Generated canonical fixtures in {FIXTURE_DIRECTORY}")


if __name__ == "__main__":
    main()
