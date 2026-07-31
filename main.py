"""MDown entry point. `flet run` / `flet build` look for this file."""

import flet as ft

from mdown_app.ui import main

ft.app(target=main)
