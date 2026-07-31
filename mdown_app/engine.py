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
import zipfile
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
            _guard_archive_bomb(path)
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


# Every format MarkItDown handles by treating the file as a zip container.
# These are the inputs a decompression bomb can hide in.
_ZIP_BASED_EXTENSIONS = frozenset(
    {".zip", ".docx", ".xlsx", ".pptx", ".epub"}
)

# Bomb-guard limits. Generous enough for real documents (a large slide deck
# with images unpacks to tens of MB), tight enough to stop a phone-killing
# expansion. Cumulative uncompressed bytes and per-member ratio both matter:
# a bomb is small on disk but enormous unpacked.
_MAX_TOTAL_UNCOMPRESSED = 300 * 1024 * 1024  # 300 MB across all members
_MAX_COMPRESSION_RATIO = 120  # uncompressed/compressed, per member
_MAX_NESTED_ARCHIVE_DEPTH = 1  # a zip inside a zip is fine; deeper is not


class ArchiveBombError(Exception):
    """Raised when an archive's declared expansion looks like a bomb."""


def _guard_archive_bomb(path: str, _depth: int = 0) -> None:
    """Reject archives whose central directory declares an implausible
    expansion, before MarkItDown decompresses anything into memory.

    Reads only the zip central directory (member metadata), never the
    compressed data, so the check itself is cheap and bomb-proof.
    """
    if Path(path).suffix.lower() not in _ZIP_BASED_EXTENSIONS:
        return
    if not zipfile.is_zipfile(path):
        return  # not actually a zip; let MarkItDown handle/reject it
    with zipfile.ZipFile(path) as zf:
        _guard_zipinfos(zf.infolist(), zf, _depth)


def _guard_zipinfos(infos, zf: zipfile.ZipFile, depth: int) -> None:
    total = 0
    for info in infos:
        if info.is_dir():
            continue
        total += info.file_size
        if total > _MAX_TOTAL_UNCOMPRESSED:
            raise ArchiveBombError(
                f"archive expands to over {_MAX_TOTAL_UNCOMPRESSED // (1024 * 1024)} MB"
            )
        if info.compress_size > 0:
            ratio = info.file_size / info.compress_size
            if ratio > _MAX_COMPRESSION_RATIO and info.file_size > 1024 * 1024:
                raise ArchiveBombError(
                    f"member '{info.filename}' has a {ratio:.0f}:1 "
                    "compression ratio"
                )
        if info.filename.lower().endswith(tuple(_ZIP_BASED_EXTENSIONS)):
            if depth + 1 > _MAX_NESTED_ARCHIVE_DEPTH:
                raise ArchiveBombError("archive nests too deeply")
            # Inspect the nested archive's own central directory in memory.
            try:
                import io

                nested = io.BytesIO(zf.read(info))
            except Exception:
                continue
            if zipfile.is_zipfile(nested):
                with zipfile.ZipFile(nested) as nzf:
                    _guard_zipinfos(nzf.infolist(), nzf, depth + 1)


def _friendly_error(exc: Exception) -> str:
    """Collapse markitdown's exception chains into one readable message."""
    if isinstance(exc, ArchiveBombError):
        return (
            "This file was blocked for safety: it looks like a "
            f"decompression bomb ({exc}). It wasn't converted."
        )
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
