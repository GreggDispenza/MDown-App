"""MDown entry point. `flet run` / `flet build` look for this file."""

import flet as ft

# On-device conversion self-test: on Android only, convert a sample off the UI
# thread and record a verdict the CI emulator smoke test reads back (see
# mdown_app/selftest.py and scripts/android_smoke.sh). No-op on desktop.
from mdown_app.selftest import maybe_run_selftest
from mdown_app.ui import main

maybe_run_selftest()

ft.app(target=main)
