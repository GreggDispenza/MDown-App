"""MDown entry point. `flet run` / `flet build` look for this file."""

import flet as ft

# On-device conversion self-test. Runs ONLY when the CI emulator smoke test
# requests it via a system property (never for real users, never on desktop);
# it converts a sample and records a verdict the smoke test reads back. See
# mdown_app/selftest.py and scripts/android_smoke.sh.
from mdown_app.selftest import run_selftest, selftest_requested
from mdown_app.ui import main

if selftest_requested():
    run_selftest()

ft.app(target=main)
