"""Engine tests: real conversions over generated fixtures.

Fixtures are generated at test time (no binaries in git). Formats needing
an optional dependency are skipped automatically when it's missing, which
mirrors how the app itself degrades per platform.
"""

import importlib.util

import pytest

from mdown_app.engine import Engine, _postprocess_pdf_markdown


@pytest.fixture(scope="module")
def engine():
    return Engine()


def test_txt(tmp_path, engine):
    p = tmp_path / "note.txt"
    p.write_text("hello markdown world", encoding="utf-8")
    res = engine.convert(str(p))
    assert res.ok, res.error
    assert "hello markdown world" in res.markdown


def test_html(tmp_path, engine):
    p = tmp_path / "page.html"
    p.write_text(
        "<html><head><title>T</title></head>"
        "<body><h1>Heading</h1><p>Body <b>bold</b>.</p></body></html>",
        encoding="utf-8",
    )
    res = engine.convert(str(p))
    assert res.ok, res.error
    assert "# Heading" in res.markdown
    assert "**bold**" in res.markdown


def test_csv(tmp_path, engine):
    p = tmp_path / "data.csv"
    p.write_text("name,qty\napples,3\npears,5\n", encoding="utf-8")
    res = engine.convert(str(p))
    assert res.ok, res.error
    assert "apples" in res.markdown and "|" in res.markdown


def test_json(tmp_path, engine):
    p = tmp_path / "conf.json"
    p.write_text('{"key": "value"}', encoding="utf-8")
    res = engine.convert(str(p))
    assert res.ok, res.error
    assert "value" in res.markdown


@pytest.mark.skipif(
    importlib.util.find_spec("openpyxl") is None, reason="openpyxl not installed"
)
def test_xlsx(tmp_path, engine):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["city", "pop"])
    ws.append(["Berlin", 3600000])
    p = tmp_path / "cities.xlsx"
    wb.save(p)
    res = engine.convert(str(p))
    assert res.ok, res.error
    assert "Berlin" in res.markdown


def test_error_is_friendly_not_raised(tmp_path, engine):
    # Non-text binary garbage with no recognizable signature.
    p = tmp_path / "broken.docx"
    p.write_bytes(bytes([0x00, 0xFE, 0x7F, 0x91]) * 64)
    res = engine.convert(str(p))
    assert not res.ok
    assert isinstance(res.error, str) and res.error


def test_formats_report():
    groups = Engine.formats()
    labels = {g.label for g in groups}
    assert "HTML" in labels and "PDF" in labels
    # Always-available groups must never be reported unavailable.
    assert all(g.available for g in groups if g.label == "HTML")


def test_picker_extensions_no_dots():
    exts = Engine.picker_extensions()
    assert "txt" in exts
    assert all(not e.startswith(".") for e in exts)


# ---- PDF markdown post-processing ----------------------------------------

def test_pdf_postprocess_promotes_section_headings():
    md = "1. Introduction\n1.1 Purpose and Scope\n2. Report Qualification\n"
    out = _postprocess_pdf_markdown(md)
    assert "# 1. Introduction" in out
    assert "## 1.1 Purpose and Scope" in out
    assert "# 2. Report Qualification" in out


def test_pdf_postprocess_strips_repeated_running_footer():
    footer = "Project number: GHK025/341/TAH / Version: F"
    md = "\n".join(
        [f"{i} {footer}\nSome body text on page {i}." for i in range(1, 7)]
    )
    out = _postprocess_pdf_markdown(md)
    assert footer not in out
    assert "Some body text on page 3." in out  # content is kept


def test_pdf_postprocess_keeps_numbered_rows_and_list_items():
    # A bare-numbered defect row (no dot) must NOT become a heading.
    md = "6 Water stains and cracks observed at window furnishing\n"
    assert not _postprocess_pdf_markdown(md).lstrip().startswith("#")
    # A long numbered sentence (list item) must NOT become a heading.
    md2 = "1. All figures are estimated based on the preliminary visual site visits.\n"
    assert not _postprocess_pdf_markdown(md2).lstrip().startswith("#")


def test_pdf_postprocess_skips_toc_entries_with_page_numbers():
    md = "4.1  Permits and Approvals, Documents Review & Compliance  10\n"
    assert not _postprocess_pdf_markdown(md).lstrip().startswith("#")


def test_pdf_postprocess_drops_standalone_page_numbers():
    md = "Real content line.\n8\nMore real content.\n"
    out = _postprocess_pdf_markdown(md)
    assert "\n8\n" not in f"\n{out}\n"
    assert "Real content line." in out and "More real content." in out
