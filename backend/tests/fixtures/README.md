# Canonical PDF fixtures

These seven files are synthetic test inputs. They contain no real candidate, employer,
education, contact, or application data. The visible phone number and email address are
documentation-only example values.

Regenerate them from the repository root with:

```bash
python scripts/generate_pdf_fixtures.py
```

The generator requires the development-only `ReportLab` dependency and uses `pypdf` to
remove metadata and validate strict parsing. It uses only fictional content. PDF object
identifiers and encryption data may vary between supported library releases, but
filenames, page counts, extractable text, and failure semantics are stable. The password
for the encrypted fixture is `fixture-password`; normal parser tests must reject it
instead of authenticating it.

Large-file and 30/31-page boundary inputs are intentionally generated in tests rather than
stored in Git.
