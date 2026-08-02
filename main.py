"""MDown entry point. `flet run` / `flet build` look for this file."""

import flet as ft

from mdown_app.ui import main

# On-device boot marker. serious_python routes stdout to Android logcat, so the
# CI emulator smoke test (scripts/android_smoke.sh) can confirm the Python
# runtime started AND the full import chain (flet + mdown_app + markitdown)
# loaded on Android by matching this line. Harmless everywhere else.
print("MDOWN_BOOT_PROBE", flush=True)

ft.app(target=main)
