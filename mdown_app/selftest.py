"""On-device conversion self-test.

The emulator smoke test (scripts/android_smoke.sh) proves the app *boots* on
Android. This proves the next thing: that a real conversion runs on-device and
produces correct Markdown. It runs a tiny CSV through the engine and records a
verdict where the CI smoke test can read it.

Reporting channel: a plain print() does NOT reach logcat under serious_python,
and flet's storage dirs are internal (not adb-readable for a release build). So
the verdict is written to the app's *external* files directory
(/storage/emulated/0/Android/data/<pkg>/files/), which adb can read without
run-as. The package name is taken from /proc/self/cmdline. The result is also
printed (it lands in flet's FLET_APP_CONSOLE log) as a fallback.

`run_selftest()` is a no-op-safe function: any failure is caught and reported
as a FAIL verdict rather than raising, so it can never crash app startup.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

RESULT_FILENAME = "mdown_selftest.txt"
# A pure-Python format (CSV) so the check never depends on a native converter
# that might be absent from the Android dependency set.
_SAMPLE_CSV = "name,qty\napples,3\npears,5\n"


def selftest_requested() -> bool:
    """True only when the CI smoke test asked for it via an Android system
    property (`setprop debug.mdown_selftest 1`). Real users never set it, and
    getprop does not exist off-Android, so this is a no-op in production and on
    desktop."""
    try:
        import subprocess

        out = subprocess.run(
            ["getprop", "debug.mdown_selftest"],
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() == "1"
    except Exception:
        return False


def _android_package() -> str:
    try:
        return Path("/proc/self/cmdline").read_bytes().split(b"\0", 1)[0].decode() or ""
    except Exception:
        return ""


def _result_paths() -> list[Path]:
    """Where to write the verdict, most-external (adb-readable) first."""
    paths: list[Path] = []
    pkg = _android_package()
    # The external files dir is only meaningful (and only adb-readable) on
    # Android; flet sets FLET_PLATFORM=android there. Guarding on it also keeps
    # the desktop/test path off the /storage/emulated tree.
    if pkg and os.environ.get("FLET_PLATFORM") == "android":
        paths.append(Path(f"/storage/emulated/0/Android/data/{pkg}/files/{RESULT_FILENAME}"))
    temp = os.environ.get("FLET_APP_STORAGE_TEMP")
    if temp:
        paths.append(Path(temp) / RESULT_FILENAME)
    data = os.environ.get("FLET_APP_STORAGE_DATA")
    if data:
        paths.append(Path(data) / RESULT_FILENAME)
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


if __name__ == "__main__":
    print(run_selftest())
