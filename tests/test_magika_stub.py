"""Tests for the magika stand-in, including the crucial integration
property: markitdown must work end-to-end with the stub instead of the
real magika (this is exactly the Android configuration)."""

import importlib
import importlib.util
import sys
import zipfile
from pathlib import Path

import pytest

STUB = (
    Path(__file__).resolve().parent.parent
    / "packaging/magika-stub/src/magika/__init__.py"
)


@pytest.fixture()
def stub(monkeypatch):
    spec = importlib.util.spec_from_file_location("magika_stub_under_test", STUB)
    module = importlib.util.module_from_spec(spec)
    # dataclass creation resolves annotations via sys.modules[cls.__module__],
    # so the module must be registered before exec.
    monkeypatch.setitem(sys.modules, "magika_stub_under_test", module)
    spec.loader.exec_module(module)
    return module


def test_pdf_signature(stub):
    res = stub.Magika().identify_bytes(b"%PDF-1.7 rest of file")
    assert res.status == "ok"
    assert res.prediction.output.label == "pdf"
    assert res.prediction.output.mime_type == "application/pdf"


def test_docx_container(stub, tmp_path):
    p = tmp_path / "f.docx"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("word/document.xml", "<w:document/>")
    res = stub.Magika().identify_path(p)
    assert res.prediction.output.label == "docx"


def test_html_text(stub):
    res = stub.Magika().identify_bytes(b"<!DOCTYPE html><html><body>x</body></html>")
    out = res.prediction.output
    assert out.label == "html" and out.is_text


def test_unknown_binary_falls_back(stub):
    res = stub.Magika().identify_bytes(bytes(range(256)) * 4)
    assert res.prediction.output.label == "unknown"


def test_stream_position_restored(stub, tmp_path):
    p = tmp_path / "a.pdf"
    p.write_bytes(b"%PDF-1.4 data")
    with open(p, "rb") as f:
        f.seek(2)
        stub.Magika().identify_stream(f)
        assert f.tell() == 2


def test_markitdown_end_to_end_with_stub(stub, tmp_path, monkeypatch):
    """Simulate Android: force markitdown to import the stub as `magika`."""
    for name in [m for m in sys.modules if m == "magika" or m.startswith("magika.")]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(sys.modules, "magika", stub)

    # Reload markitdown so its module-level `import magika` binds the stub.
    for name in [m for m in list(sys.modules) if m.startswith("markitdown")]:
        monkeypatch.delitem(sys.modules, name)
    markitdown = importlib.import_module("markitdown")

    p = tmp_path / "doc.html"
    p.write_text("<html><body><h2>Stub works</h2></body></html>", encoding="utf-8")
    md = markitdown.MarkItDown(enable_plugins=False)
    assert md._magika.__class__.__module__ == stub.__name__  # really the stub
    result = md.convert(str(p))
    assert "## Stub works" in result.markdown
