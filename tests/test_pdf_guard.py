"""Tests for the PDF resource-exhaustion guard in the engine."""

import pytest

import mdown_app.engine as engine
from mdown_app.engine import Engine, PdfBombError, _guard_pdf, _pdf_page_count


def _make_pdf(path, page_count, pad=0):
    """Write a minimal but structurally valid PDF whose page tree declares
    `page_count` pages. `pad` appends filler bytes to inflate the file size."""
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count %d >>" % page_count,
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>",
    ]
    body = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objs, start=1):
        offsets.append(len(body))
        body += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref_pos = len(body)
    n = len(objs) + 1
    body += b"xref\n0 %d\n" % n
    body += b"0000000000 65535 f \n"
    for off in offsets:
        body += b"%010d 00000 n \n" % off
    body += b"trailer\n<< /Root 1 0 R /Size %d >>\nstartxref\n%d\n%%%%EOF" % (
        n,
        xref_pos,
    )
    if pad:
        body += b"\n%" + b"\x00" * pad
    path.write_bytes(bytes(body))


def test_normal_pdf_passes(tmp_path):
    p = tmp_path / "ok.pdf"
    _make_pdf(p, page_count=3)
    _guard_pdf(str(p))  # must not raise


def test_page_count_read_from_page_tree(tmp_path):
    p = tmp_path / "counted.pdf"
    _make_pdf(p, page_count=42)
    # Read straight from /Count without walking pages.
    assert _pdf_page_count(str(p)) == 42


def test_absurd_page_count_blocked(tmp_path):
    p = tmp_path / "pagebomb.pdf"
    _make_pdf(p, page_count=engine._MAX_PDF_PAGES + 1)
    with pytest.raises(PdfBombError):
        _guard_pdf(str(p))


def test_oversized_pdf_blocked(tmp_path, monkeypatch):
    # Use a tiny cap so the test file stays small instead of writing 200 MB.
    monkeypatch.setattr(engine, "_MAX_PDF_BYTES", 4 * 1024)
    p = tmp_path / "big.pdf"
    _make_pdf(p, page_count=1, pad=16 * 1024)
    with pytest.raises(PdfBombError):
        _guard_pdf(str(p))


def test_unreadable_pdf_count_is_ignored(tmp_path):
    # Junk with a .pdf extension: page count can't be read, so the page-count
    # guard is skipped (size guard still applies) and this must not raise.
    p = tmp_path / "junk.pdf"
    p.write_bytes(b"not a pdf at all")
    assert _pdf_page_count(str(p)) is None
    _guard_pdf(str(p))  # must not raise


def test_non_pdf_ignored(tmp_path):
    p = tmp_path / "note.txt"
    p.write_text("hello")
    _guard_pdf(str(p))  # must not raise


def test_engine_returns_friendly_pdf_error(tmp_path):
    p = tmp_path / "pagebomb.pdf"
    _make_pdf(p, page_count=engine._MAX_PDF_PAGES + 1)
    res = Engine().convert(str(p))
    assert not res.ok
    assert "blocked for safety" in res.error
    assert "pages" in res.error
