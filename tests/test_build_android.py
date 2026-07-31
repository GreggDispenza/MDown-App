"""Regression tests for scripts/build_android.py's pyproject rewriting."""

import shutil
import sys
from pathlib import Path

import tomllib

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import build_android  # noqa: E402


def _rewritten(tmp_path) -> str:
    shutil.copy(REPO / "pyproject.toml", tmp_path / "pyproject.toml")
    build_android.rewrite_pyproject(tmp_path)
    return (tmp_path / "pyproject.toml").read_text()


def test_rewrite_produces_valid_toml(tmp_path):
    data = tomllib.loads(_rewritten(tmp_path))
    deps = data["project"]["dependencies"]
    assert any(d.startswith("flet==") for d in deps)
    assert any(d.startswith("magika @ file://") for d in deps)
    # The full-extras markitdown must have been replaced by the pure set.
    assert not any("pptx" in d or "pdf" in d for d in deps)


def test_rewrite_leaves_no_remnant(tmp_path):
    # The original bug: a lazy regex stopped at the ']' inside
    # "markitdown[docx,...]" and left a dangling ']==0.1.7",' line.
    text = _rewritten(tmp_path)
    # The bug left a dangling array-close fused to a version spec on its
    # own line, e.g. ']==0.1.7",'. A legitimate ']==' occurs inside a
    # dependency string like "markitdown[...]==0.1.7", so check line starts.
    for line in text.splitlines():
        assert not line.lstrip().startswith("]=="), "dangling remnant: " + line
    assert text.count("dependencies = [") == 1


def test_pyproject_parses_with_legacy_toml_semantics():
    # flet's CLI uses the old `toml` package, which chokes on quotes and
    # apostrophes in comments inside arrays. Guard: no comment lines
    # between the dependencies array's brackets.
    lines = (REPO / "pyproject.toml").read_text().splitlines()
    inside = False
    for line in lines:
        if line.startswith("dependencies = ["):
            inside = True
            continue
        if inside and line.startswith("]"):
            break
        if inside:
            assert not line.strip().startswith("#"), (
                "no comments allowed inside dependencies array: " + line
            )
