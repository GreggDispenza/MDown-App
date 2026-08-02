"""On-device conversion self-test.

The emulator smoke test (scripts/android_smoke.sh) proves the app *boots* on
Android. This proves the next thing: that a real conversion runs there and
produces correct Markdown. It converts a tiny CSV through the engine and writes
a verdict (MDOWN_SELFTEST OK len=.. sha=..) that the smoke test reads back.

Reporting channel: a release app is an `untrusted_app` under SELinux, so it
cannot exec system tools, read /proc/self/cmdline, or write adb-readable
external storage; and its stdout does not reach logcat. What it *can* always do
is write to its own internal storage (flet exposes those dirs as
FLET_APP_STORAGE_DATA / FLET_APP_STORAGE_TEMP). The CI emulator is a rootable
`google_apis` image, so the smoke test reads that internal file via `adb root`.

`run_selftest()` never raises — any failure becomes a FAIL verdict — so it can
never crash app startup. `maybe_run_selftest()` runs it (off the UI thread) only
on Android; it is a no-op on desktop and in tests.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import threading
from pathlib import Path

RESULT_FILENAME = "mdown_selftest.txt"
# A pure-Python format (CSV) so the check never depends on a native converter
# that might be absent from the Android dependency set.
_SAMPLE_CSV = "name,qty\napples,3\npears,5\n"


def _result_paths() -> list[Path]:
    """App-private locations to write the verdict, in preference order."""
    paths: list[Path] = []
    for env in ("FLET_APP_STORAGE_DATA", "FLET_APP_STORAGE_TEMP"):
        value = os.environ.get(env)
        if value:
            paths.append(Path(value) / RESULT_FILENAME)
    if not paths:  # desktop / tests
        paths.append(Path(tempfile.gettempdir()) / RESULT_FILENAME)
    return paths


def _run() -> str:
    """Convert a sample and return a one-line verdict string."""
    from .engine import Engine

    tmpdir = os.environ.get("FLET_APP_STORAGE_TEMP") or tempfile.gettempdir()
    src = Path(tmpdir) / "mdown_selftest_sample.csv"
    src.write_text(_SAMPLE_CSV, encoding="utf-8")

    res = Engine().convert(str(src))
    md = res.markdown if res.ok else ""
    ok = bool(res.ok) and "apples" in md and "pears" in md and "|" in md
    digest = hashlib.sha256(md.encode("utf-8")).hexdigest()[:8]
    return f"MDOWN_SELFTEST {'OK' if ok else 'FAIL'} len={len(md)} sha={digest}"


def run_selftest() -> str:
    """Run the self-test, record the verdict, and return it. Never raises."""
    try:
        verdict = _run()
    except Exception as exc:  # pragma: no cover - defensive
        verdict = f"MDOWN_SELFTEST FAIL error={type(exc).__name__}:{exc}"
    print(verdict, flush=True)
    for path in _result_paths():
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(verdict + "\n", encoding="utf-8")
            break  # first writable location wins
        except Exception:
            continue
    return verdict


def maybe_run_selftest() -> None:
    """On Android, run the self-test off the UI thread so it never delays first
    paint; a no-op everywhere else. flet sets FLET_PLATFORM=android on-device."""
    if os.environ.get("FLET_PLATFORM") == "android":
        threading.Thread(target=run_selftest, name="mdown-selftest", daemon=True).start()


if __name__ == "__main__":
    print(run_selftest())
