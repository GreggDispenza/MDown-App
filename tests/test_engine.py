"""Engine tests: real conversions over generated fixtures.

Fixtures are generated at test time (no binaries in git). Formats needing
an optional dependency are skipped automatically when it's missing, which
mirrors how the app itself degrades per platform.
"""

import importlib.util

import pytest

from mdown_app.engine import Engine


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
