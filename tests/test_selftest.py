"""Tests for the on-device conversion self-test (mdown_app.selftest).

The conversion logic is platform-independent, so it is verified here on the
desktop; only the Android reporting channel differs at runtime.
"""

from mdown_app import selftest


def test_run_selftest_converts_and_reports_ok(tmp_path, monkeypatch):
    # Keep the verdict file inside the test's tmp dir.
    monkeypatch.setenv("FLET_APP_STORAGE_TEMP", str(tmp_path))
    verdict = selftest.run_selftest()
    assert verdict.startswith("MDOWN_SELFTEST OK"), verdict
    assert "len=" in verdict and "sha=" in verdict
    # The verdict was written where the smoke test would read it.
    assert (tmp_path / selftest.RESULT_FILENAME).read_text().strip() == verdict


def test_selftest_requested_false_without_property():
    # No Android getprop on the desktop -> never requested (production-safe).
    assert selftest.selftest_requested() is False


def test_run_selftest_never_raises(monkeypatch):
    # Even if the engine blows up, run_selftest reports FAIL rather than raising.
    monkeypatch.setattr(
        "mdown_app.selftest._run", lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    verdict = selftest.run_selftest()
    assert verdict.startswith("MDOWN_SELFTEST FAIL")
