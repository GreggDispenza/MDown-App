#!/usr/bin/env python3
"""Cut a release: bump the version, commit, and tag.

Pushing the resulting `vX.Y.Z` tag triggers the CI Android job, which builds
a signed AAB (versionCode = CI run number) and — when configured — uploads it
to Play's internal track. See docs/play-release-checklist.md.

Usage:
    python scripts/release.py patch          # 0.1.0 -> 0.1.1
    python scripts/release.py minor          # 0.1.0 -> 0.2.0
    python scripts/release.py major          # 0.1.0 -> 1.0.0
    python scripts/release.py 0.4.2          # explicit version
    python scripts/release.py patch --push   # also push branch + tag
    python scripts/release.py patch --dry-run # preview only

By default it rewrites pyproject.toml, commits, and creates an annotated tag
locally; add --push to publish. Refuses to run on a dirty tree or if the tag
already exists.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PYPROJECT = REPO / "pyproject.toml"
SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
VERSION_LINE = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)


def read_version(text: str) -> str:
    m = VERSION_LINE.search(text)
    if not m:
        sys.exit("error: could not find version in pyproject.toml")
    return m.group(1)


def bump_version(current: str, spec: str) -> str:
    """Return the next version for a bump level or an explicit X.Y.Z."""
    m = SEMVER.match(current)
    if not m:
        sys.exit(f"error: current version {current!r} is not MAJOR.MINOR.PATCH")
    major, minor, patch = (int(x) for x in m.groups())
    if spec == "major":
        return f"{major + 1}.0.0"
    if spec == "minor":
        return f"{major}.{minor + 1}.0"
    if spec == "patch":
        return f"{major}.{minor}.{patch + 1}"
    if not SEMVER.match(spec):
        sys.exit(f"error: {spec!r} is not a bump level (major/minor/patch) or X.Y.Z")
    if _tuple(spec) <= _tuple(current):
        sys.exit(f"error: {spec} is not greater than current {current}")
    return spec


def _tuple(v: str) -> tuple[int, int, int]:
    return tuple(int(x) for x in SEMVER.match(v).groups())  # type: ignore[union-attr]


def _git(*args: str, check: bool = True) -> str:
    r = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)
    if check and r.returncode != 0:
        sys.exit(f"error: git {' '.join(args)}\n{r.stderr.strip()}")
    return r.stdout.strip()


def main() -> None:
    ap = argparse.ArgumentParser(description="Bump version, commit, and tag a release.")
    ap.add_argument("spec", help="major | minor | patch | explicit X.Y.Z")
    ap.add_argument("--push", action="store_true", help="push the branch and tag")
    ap.add_argument("--dry-run", action="store_true", help="preview without changing anything")
    args = ap.parse_args()

    text = PYPROJECT.read_text()
    current = read_version(text)
    new = bump_version(current, args.spec)
    tag = f"v{new}"
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")

    print(f"Version : {current} -> {new}")
    print(f"Tag     : {tag}")
    print(f"Branch  : {branch}")

    if args.dry_run:
        print("(dry run — no changes made)")
        return

    if _git("status", "--porcelain"):
        sys.exit("error: working tree is dirty; commit or stash first")
    if _git("tag", "--list", tag):
        sys.exit(f"error: tag {tag} already exists")

    PYPROJECT.write_text(VERSION_LINE.sub(f'version = "{new}"', text, count=1))
    _git("add", "pyproject.toml")
    _git("commit", "-m", f"Release {tag}")
    _git("tag", "-a", tag, "-m", f"Release {tag}")
    print(f"Committed and tagged {tag}.")

    if args.push:
        _git("push", "origin", branch)
        _git("push", "origin", tag)
        print(f"Pushed {branch} and {tag} — CI will build the signed AAB.")
    else:
        print(f"Next: git push origin {branch} && git push origin {tag}")


if __name__ == "__main__":
    main()
