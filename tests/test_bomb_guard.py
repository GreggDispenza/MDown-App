"""Tests for the decompression-bomb guard in the engine."""

import io
import zipfile

import pytest

from mdown_app.engine import ArchiveBombError, Engine, _guard_archive_bomb


def _make_zip(path, members):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in members.items():
            z.writestr(name, data)


def test_normal_zip_passes(tmp_path):
    p = tmp_path / "ok.zip"
    _make_zip(p, {"a.txt": "hello", "b.txt": "world"})
    _guard_archive_bomb(str(p))  # must not raise


def test_high_ratio_member_blocked(tmp_path):
    # 8 MB of zeros compresses to a few KB — ratio far over the limit.
    p = tmp_path / "bomb.zip"
    _make_zip(p, {"payload.bin": b"\x00" * (8 * 1024 * 1024)})
    with pytest.raises(ArchiveBombError):
        _guard_archive_bomb(str(p))


def test_oversized_total_blocked(tmp_path):
    p = tmp_path / "big.zip"
    # Many members of incompressible-ish size to blow the 300 MB total
    # without any single member tripping the ratio rule.
    import os

    with zipfile.ZipFile(p, "w", zipfile.ZIP_STORED) as z:
        for i in range(7):
            z.writestr(f"m{i}.bin", os.urandom(50 * 1024 * 1024))
    with pytest.raises(ArchiveBombError):
        _guard_archive_bomb(str(p))


def test_deeply_nested_blocked(tmp_path):
    # zip -> zip -> zip exceeds depth 1.
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as z:
        z.writestr("deep.txt", "x")
    mid = io.BytesIO()
    with zipfile.ZipFile(mid, "w") as z:
        z.writestr("inner.zip", inner.getvalue())
    p = tmp_path / "outer.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("mid.zip", mid.getvalue())
    with pytest.raises(ArchiveBombError):
        _guard_archive_bomb(str(p))


def test_zip_containing_one_docx_ok(tmp_path):
    # One level of nesting (zip holding a docx) is allowed.
    docx = io.BytesIO()
    with zipfile.ZipFile(docx, "w") as z:
        z.writestr("word/document.xml", "<w:document/>")
    p = tmp_path / "bundle.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("report.docx", docx.getvalue())
    _guard_archive_bomb(str(p))  # must not raise


def test_non_archive_ignored(tmp_path):
    p = tmp_path / "note.txt"
    p.write_text("not a zip")
    _guard_archive_bomb(str(p))  # must not raise


def test_engine_returns_friendly_bomb_error(tmp_path):
    p = tmp_path / "bomb.zip"
    _make_zip(p, {"payload.bin": b"\x00" * (8 * 1024 * 1024)})
    res = Engine().convert(str(p))
    assert not res.ok
    assert "decompression bomb" in res.error
