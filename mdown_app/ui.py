"""MDown UI — one screen to pick files, one screen to read the result.

Deliberately small: two views swapped inside a single Flet page, no
routing, no state beyond the current result list. Anything conversion-
related lives in `mdown_app.engine`; this module only talks to the user.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

import flet as ft

from .engine import ConversionResult, Engine
from .storage import pick_mobile_save_dir


class MDownApp:
    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.engine = Engine()
        self.results: List[ConversionResult] = []
        self.current: Optional[ConversionResult] = None

        page.title = "MDown — Anything to Markdown"
        page.theme_mode = ft.ThemeMode.SYSTEM
        page.theme = ft.Theme(color_scheme_seed=ft.Colors.INDIGO)
        page.padding = 0

        self.pick_dialog = ft.FilePicker(on_result=self._on_files_picked)
        self.save_dialog = ft.FilePicker(on_result=self._on_save_location)
        page.overlay.extend([self.pick_dialog, self.save_dialog])

        page.appbar = ft.AppBar(
            leading=ft.Icon(ft.Icons.SWAP_HORIZ),
            title=ft.Text("MDown", weight=ft.FontWeight.BOLD),
            center_title=False,
            actions=[
                ft.IconButton(
                    ft.Icons.BRIGHTNESS_6_OUTLINED,
                    tooltip="Light / dark",
                    on_click=self._toggle_theme,
                )
            ],
        )

        self.body = ft.Container(expand=True, padding=16)
        page.add(ft.SafeArea(self.body, expand=True))
        self._show_home()

    # ------------------------------------------------------------- views

    def _show_home(self, _=None) -> None:
        self.current = None
        chips = [
            ft.Chip(
                label=ft.Text(g.label),
                disabled=not g.available,
                tooltip=", ".join(g.extensions)
                if g.available
                else "Not available in this build",
            )
            for g in self.engine.formats()
        ]
        self.body.content = ft.Column(
            [
                ft.Container(height=24),
                ft.Icon(ft.Icons.DESCRIPTION_OUTLINED, size=64),
                ft.Text(
                    "Convert documents to Markdown",
                    size=22,
                    weight=ft.FontWeight.W_600,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    "Pick one or more files. Everything happens on this "
                    "device — nothing is uploaded.",
                    text_align=ft.TextAlign.CENTER,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Container(height=8),
                ft.FilledButton(
                    "Choose files",
                    icon=ft.Icons.FOLDER_OPEN,
                    on_click=lambda _: self.pick_dialog.pick_files(
                        allow_multiple=True,
                        allowed_extensions=self.engine.picker_extensions(),
                    ),
                ),
                ft.Container(height=16),
                ft.Text("Supported on this device:", size=12),
                ft.Row(chips, wrap=True, alignment=ft.MainAxisAlignment.CENTER),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )
        self.page.update()

    def _show_busy(self, n: int) -> None:
        self.body.content = ft.Column(
            [
                ft.ProgressRing(),
                ft.Text(f"Converting {n} file{'s' if n > 1 else ''}…"),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            expand=True,
        )
        self.page.update()

    def _show_list(self) -> None:
        """Overview when several files were converted."""
        tiles = []
        for res in self.results:
            tiles.append(
                ft.ListTile(
                    leading=ft.Icon(
                        ft.Icons.CHECK_CIRCLE if res.ok else ft.Icons.ERROR,
                        color=ft.Colors.GREEN if res.ok else ft.Colors.ERROR,
                    ),
                    title=ft.Text(res.name),
                    subtitle=ft.Text(
                        f"{len(res.markdown):,} characters · {res.seconds:.1f}s"
                        if res.ok
                        else res.error,
                        max_lines=2,
                    ),
                    on_click=(lambda r: lambda _: self._show_result(r))(res),
                )
            )
        self.body.content = ft.Column(
            [
                ft.Row(
                    [
                        ft.IconButton(ft.Icons.ARROW_BACK, on_click=self._show_home),
                        ft.Text("Results", size=18, weight=ft.FontWeight.W_600),
                    ]
                ),
                ft.ListView(tiles, expand=True, spacing=4),
            ],
            expand=True,
        )
        self.page.update()

    def _show_result(self, res: ConversionResult) -> None:
        self.current = res
        back = self._show_list if len(self.results) > 1 else self._show_home

        if not res.ok:
            self.body.content = ft.Column(
                [
                    ft.Row(
                        [
                            ft.IconButton(ft.Icons.ARROW_BACK, on_click=back),
                            ft.Text(res.name, size=16, weight=ft.FontWeight.W_600),
                        ]
                    ),
                    ft.Icon(ft.Icons.ERROR_OUTLINE, size=48, color=ft.Colors.ERROR),
                    ft.Text("Couldn't convert this file", size=18),
                    ft.Text(res.error, text_align=ft.TextAlign.CENTER),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True,
            )
            self.page.update()
            return

        preview = ft.Container(
            ft.Column(
                [
                    ft.Markdown(
                        res.markdown,
                        selectable=True,
                        extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                    )
                ],
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
            padding=8,
            expand=True,
        )
        raw = ft.TextField(
            value=res.markdown,
            multiline=True,
            read_only=True,
            expand=True,
            text_style=ft.TextStyle(font_family="monospace", size=13),
            border=ft.InputBorder.NONE,
        )
        self.body.content = ft.Column(
            [
                ft.Row(
                    [
                        ft.IconButton(ft.Icons.ARROW_BACK, on_click=back),
                        ft.Text(
                            res.name,
                            size=16,
                            weight=ft.FontWeight.W_600,
                            expand=True,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                    ]
                ),
                ft.Tabs(
                    tabs=[
                        ft.Tab(text="Preview", icon=ft.Icons.VISIBILITY, content=preview),
                        ft.Tab(text="Markdown", icon=ft.Icons.CODE, content=raw),
                    ],
                    expand=True,
                ),
                ft.Row(
                    [
                        ft.OutlinedButton(
                            "Copy", icon=ft.Icons.COPY, on_click=self._copy_current
                        ),
                        ft.FilledButton(
                            "Save .md",
                            icon=ft.Icons.SAVE_ALT,
                            on_click=self._save_current,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=12,
                ),
                ft.Container(height=8),
            ],
            expand=True,
        )
        self.page.update()

    # ----------------------------------------------------------- actions

    def _toggle_theme(self, _) -> None:
        self.page.theme_mode = (
            ft.ThemeMode.DARK
            if self.page.theme_mode != ft.ThemeMode.DARK
            else ft.ThemeMode.LIGHT
        )
        self.page.update()

    def _on_files_picked(self, e: ft.FilePickerResultEvent) -> None:
        if not e.files:
            return
        paths = [f.path for f in e.files if f.path]
        self._show_busy(len(paths))
        # Conversion can take seconds (PDFs); keep the UI thread free.
        self.page.run_thread(self._convert_all, paths)

    def _convert_all(self, paths: List[str]) -> None:
        self.results = [self.engine.convert(p) for p in paths]
        if len(self.results) == 1:
            self._show_result(self.results[0])
        else:
            self._show_list()

    def _copy_current(self, _) -> None:
        if self.current and self.current.ok:
            self.page.set_clipboard(self.current.markdown)
            self._toast("Markdown copied to clipboard")

    def _default_md_name(self) -> str:
        return Path(self.current.source).stem + ".md"

    def _save_current(self, _) -> None:
        if not (self.current and self.current.ok):
            return
        if self.page.platform in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS):
            # No usable native save dialog on mobile (Flet 0.28.3's save_file
            # can't write through SAF). Prefer the app's external files dir,
            # which a file manager can open, over unreachable internal storage;
            # be honest when we can only reach the latter.
            internal = os.environ.get("FLET_APP_STORAGE_DATA") or str(Path.home())
            base, reachable = pick_mobile_save_dir(internal)
            target = Path(base) / self._default_md_name()
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(self.current.markdown, encoding="utf-8")
            except OSError as exc:
                self._toast(f"Couldn't save the file ({exc}). Use Copy instead.")
                return
            if reachable:
                self._toast(f"Saved to {target}")
            else:
                self._toast(
                    "Saved, but only inside the app's private storage, which a "
                    "file manager can't open. Use Copy to get the Markdown out."
                )
        else:
            self.save_dialog.save_file(
                dialog_title="Save Markdown",
                file_name=self._default_md_name(),
                allowed_extensions=["md"],
            )

    def _on_save_location(self, e: ft.FilePickerResultEvent) -> None:
        if e.path and self.current and self.current.ok:
            path = e.path if e.path.endswith(".md") else e.path + ".md"
            Path(path).write_text(self.current.markdown, encoding="utf-8")
            self._toast(f"Saved to {path}")

    def _toast(self, message: str) -> None:
        self.page.open(ft.SnackBar(ft.Text(message)))


def main(page: ft.Page) -> None:
    MDownApp(page)
