"""Conversion engine: a thin, defensive wrapper around MarkItDown.

Responsibilities:
- make `import markitdown` succeed even when the real `magika` package is
  unavailable (see `_ensure_magika`);
- expose a small, UI-friendly API: `convert(path) -> ConversionResult`;
- report which optional converters are actually usable on this device so
  the UI can tell the user up front.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


def _ensure_magika() -> None:
    """Guarantee that `import magika` works before importing markitdown.

    Preference order:
    1. whatever `magika` is installed (real one, or our stub package from
       packaging/magika-stub — same API either way);
    2. when running from a source checkout without any magika installed,
       load the stub implementation straight from the repo;
    3. as a last resort, register a minimal module whose Magika always
       answers "unknown", which makes markitdown rely purely on filename
       extensions. The app still works; detection is just less clever.
    """
    if importlib.util.find_spec("magika") is not None:
        return

    repo_stub = Path(__file__).resolve().parent.parent / (
        "packaging/magika-stub/src/magika/__init__.py"
    )
    if repo_stub.exists():
        spec = importlib.util.spec_from_file_location("magika", repo_stub)
        module = importlib.util.module_from_spec(spec)
        sys.modules["magika"] = module
        spec.loader.exec_module(module)
        return

    import types

    module = types.ModuleType("magika")

    class _Output:
        label = "unknown"
        mime_type = "application/octet-stream"
        is_text = False
        extensions: list = []

    class _Prediction:
        output = _Output()
        score = 1.0

    class _Result:
        status = "ok"
        prediction = _Prediction()

    class Magika:  # noqa: N801 - mirrors the real class name
        def __init__(self, *a, **k):
            pass

        def identify_stream(self, stream):
            return _Result()

        def identify_bytes(self, data):
            return _Result()

    module.Magika = Magika
    sys.modules["magika"] = module


_ensure_magika()

from markitdown import MarkItDown  # noqa: E402  (must come after _ensure_magika)


@dataclass
class ConversionResult:
    source: str
    markdown: str = ""
    title: Optional[str] = None
    error: Optional[str] = None
    seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def name(self) -> str:
        return Path(self.source).name


# Format groups the UI advertises. Each entry: (label, extensions, module
# whose importability decides availability; None = always available).
_FORMAT_GROUPS = [
    ("Text / Markdown", [".txt", ".md"], None),
    ("HTML", [".html", ".htm"], None),
    ("CSV", [".csv"], None),
    ("JSON / XML", [".json", ".xml"], None),
    ("Word", [".docx"], "mammoth"),
    ("Excel", [".xlsx"], "openpyxl"),
    ("Excel 97-2003", [".xls"], "xlrd"),
    ("PowerPoint", [".pptx"], "pptx"),
    ("PDF", [".pdf"], "pdfminer"),
    ("Outlook e-mail", [".msg"], "olefile"),
    ("EPub", [".epub"], None),
    ("Jupyter notebook", [".ipynb"], None),
    ("Zip archive", [".zip"], None),
]


@dataclass
class FormatGroup:
    label: str
    extensions: List[str]
    available: bool = True


class Engine:
    """One MarkItDown instance, reused across conversions (it is stateless
    per call, and constructing it repeatedly re-probes converter plugins)."""

    def __init__(self) -> None:
        self._md = MarkItDown(enable_plugins=False)

    def convert(self, path: str) -> ConversionResult:
        started = time.monotonic()
        try:
            result = self._md.convert(path)
            return ConversionResult(
                source=path,
                markdown=result.markdown,
                title=result.title,
                seconds=time.monotonic() - started,
            )
        except Exception as exc:  # markitdown raises many exception types
            return ConversionResult(
                source=path,
                error=_friendly_error(exc),
                seconds=time.monotonic() - started,
            )

    @staticmethod
    def formats() -> List[FormatGroup]:
        groups = []
        for label, exts, probe in _FORMAT_GROUPS:
            available = probe is None or importlib.util.find_spec(probe) is not None
            groups.append(FormatGroup(label, exts, available))
        return groups

    @staticmethod
    def picker_extensions() -> List[str]:
        """Flat extension list (no dots) for the file picker, available only."""
        exts: List[str] = []
        for group in Engine.formats():
            if group.available:
                exts.extend(e.lstrip(".") for e in group.extensions)
        return exts


def _friendly_error(exc: Exception) -> str:
    """Collapse markitdown's exception chains into one readable message."""
    text = str(exc).strip()
    if "UnsupportedFormatException" in type(exc).__name__ or "not supported" in text:
        return (
            "This file type isn't supported on this device. "
            "See the format list on the start screen."
        )
    if "MissingDependencyException" in type(exc).__name__:
        return (
            "The converter for this file type isn't installed in this build. "
            + text.splitlines()[0]
        )
    if not text:
        text = traceback.format_exception_only(type(exc), exc)[-1].strip()
    return text
