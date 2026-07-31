#!/usr/bin/env python3
"""Build the Android APK with the pure-Python dependency set.

Use this when the default `flet build apk` fails because pip cannot
resolve native dependencies (onnxruntime, pulled in by magika) for the
Android target. It:

1. copies the project to a scratch build directory (so the real
   pyproject.toml is untouched);
2. rewrites the copy's [project] dependencies to the pure-Python set from
   requirements-android.txt, substituting our local magika stand-in
   (packaging/magika-stub) for the real magika;
3. runs `flet build apk` there and reports where the APK landed.

Prerequisites: Flutter SDK + Android toolchain on PATH (see
docs/BUILDING.md). Run from anywhere:  python scripts/build_android.py
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EXCLUDE = {".git", ".venv", "venv", "build", "dist", "__pycache__", ".flet"}


def android_dependencies() -> list[str]:
    deps = []
    for line in (REPO / "requirements-android.txt").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            deps.append(line)
    stub = (REPO / "packaging/magika-stub").as_uri()  # file:///... absolute
    deps.append(f"magika @ {stub}")
    return deps


def rewrite_pyproject(build_dir: Path) -> None:
    pyproject = build_dir / "pyproject.toml"
    text = pyproject.read_text()
    dep_lines = "\n".join(f'    "{d}",' for d in android_dependencies())
    # Match through the array's closing bracket at the start of a line —
    # a lazy `.*?\]` would stop at the `]` inside extras like
    # "markitdown[docx,xlsx]" and corrupt the file.
    text, n = re.subn(
        r"dependencies = \[.*?\n\]",
        "dependencies = [\n" + dep_lines + "\n]",
        text,
        count=1,
        flags=re.DOTALL,
    )
    if n != 1:
        sys.exit("error: could not find [project] dependencies in pyproject.toml")
    pyproject.write_text(text)


def main() -> None:
    build_root = Path(tempfile.mkdtemp(prefix="mdown-android-"))
    build_dir = build_root / "app"
    shutil.copytree(
        REPO, build_dir, ignore=lambda d, names: [n for n in names if n in EXCLUDE]
    )
    rewrite_pyproject(build_dir)
    print(f"Building in {build_dir} (original project untouched)")

    result = subprocess.run(
        ["flet", "build", "apk", *sys.argv[1:]], cwd=build_dir
    )
    if result.returncode != 0:
        sys.exit(result.returncode)

    apk_dir = build_dir / "build" / "apk"
    out = REPO / "dist" / "android"
    out.mkdir(parents=True, exist_ok=True)
    for apk in apk_dir.glob("*.apk"):
        shutil.copy2(apk, out / apk.name)
        print(f"APK: {out / apk.name}")


if __name__ == "__main__":
    main()
