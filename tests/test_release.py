"""Tests for scripts/release.py version logic."""

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import release  # noqa: E402


def test_bump_levels():
    assert release.bump_version("0.1.0", "patch") == "0.1.1"
    assert release.bump_version("0.1.0", "minor") == "0.2.0"
    assert release.bump_version("0.1.0", "major") == "1.0.0"
    assert release.bump_version("1.9.9", "minor") == "1.10.0"


def test_bump_explicit_version():
    assert release.bump_version("0.1.0", "0.4.2") == "0.4.2"


def test_bump_rejects_non_increasing_explicit():
    with pytest.raises(SystemExit):
        release.bump_version("0.2.0", "0.1.0")
    with pytest.raises(SystemExit):
        release.bump_version("0.2.0", "0.2.0")


def test_bump_rejects_garbage_spec():
    with pytest.raises(SystemExit):
        release.bump_version("0.1.0", "1.2")
    with pytest.raises(SystemExit):
        release.bump_version("0.1.0", "banana")


def test_read_version_matches_pyproject():
    text = (REPO / "pyproject.toml").read_text()
    v = release.read_version(text)
    assert release.SEMVER.match(v), f"pyproject version {v!r} must be X.Y.Z"
