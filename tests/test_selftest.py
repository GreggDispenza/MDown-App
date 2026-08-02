"""Tests for the on-device conversion self-test (mdown_app.selftest).

The conversion logic is platform-independent, so it is verified here on the
desktop; only the Android reporting channel differs at runtime.
"""

import time

from mdown_app import selftest


def test_run_selftest_converts_and_reports_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path))
    verdict = selftest.run_selftest()
    assert verdict.startswith("MDOWN_SELFTEST OK"), verdict
    assert "len=" in verdict and "sha=" in verdict
    # The verdict was written where the smoke test would read it.
    assert (tmp_path / selftest.RESULT_FILENAME).read_text().strip() == verdict


def test_run_selftest_never_raises(monkeypatch):
    # Even if the engine blows up, run_selftest reports FAIL rather than raising.
    monkeypatch.setattr(
        "mdown_app.selftest._run", lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    verdict = selftest.run_selftest()
    assert verdict.startswith("MDOWN_SELFTEST FAIL")


def test_maybe_run_selftest_is_noop_off_android(tmp_path, monkeypatch):
    monkeypatch.delenv("FLET_PLATFORM", raising=False)
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path))
    selftest.maybe_run_selftest()
    assert not (tmp_path / selftest.RESULT_FILENAME).exists()


def test_maybe_run_selftest_runs_on_android(tmp_path, monkeypatch):
    monkeypatch.setenv("FLET_PLATFORM", "android")
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path))
    selftest.maybe_run_selftest()
    result = tmp_path / selftest.RESULT_FILENAME
    for _ in range(50):  # the self-test runs on a background thread
        if result.exists():
            break
        time.sleep(0.1)
    assert result.read_text().startswith("MDOWN_SELFTEST OK")
