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
import re
import sys
import time
import traceback
import zipfile
from collections import Counter
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
            markdown = result.markdown
            # MarkItDown's PDF path emits flat text: no heading markup, and
            # the page's running header/footer repeated at every page break.
            # Tidy that up so PDF output is navigable Markdown, not a text
            # dump. Other formats already convert to good Markdown, so we
            # leave them untouched.
            if Path(path).suffix.lower() == ".pdf":
                markdown = _postprocess_pdf_markdown(markdown)
                markdown = _insert_risk_tables(markdown, path)
            return ConversionResult(
                source=path,
                markdown=markdown,
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


# ---- PDF markdown tidy-up -------------------------------------------------
# A running header/footer is a line that repeats on most pages (e.g. a
# confidential banner or a "Project number: ... / Version: ..." footer). We
# detect them by how often an identical line recurs, ignoring any leading
# page number that varies per page. Only reasonably long lines qualify, so
# short repeated content (a "L" risk level, a "10" item number) is never
# mistaken for boilerplate.
_RUNNING_MARK_MIN_COUNT = 4
_RUNNING_MARK_MIN_LEN = 12

# A heading line looks like "1. Introduction", "2.1 Use of This Report" or
# "4.1  Permits and Approvals": a dotted section number followed by a short
# title. We require the number to carry a dot (trailing, like "5.", or
# internal, like "1.1") so bare-numbered defect rows ("6 Water stains ...")
# are not promoted, and we reject long, sentence-like text so numbered list
# items ("1. All figures are estimated ...") stay as body text.
_SECTION_RE = re.compile(r"^(\d+(?:\.\d+)*)(\.)?\s+(\S.*)$")
_HEADING_MAX_LEN = 60
_HEADING_MAX_WORDS = 9


def _strip_leading_page_number(line: str) -> str:
    return re.sub(r"^\s*\d+\s+", "", line).strip()


def _maybe_heading(line: str) -> str:
    stripped = line.strip()
    if stripped.startswith(("|", "#")):
        return line  # already a table row or a heading
    m = _SECTION_RE.match(stripped)
    if not m:
        return line
    number, trailing_dot, title = m.group(1), m.group(2), m.group(3).strip()
    if trailing_dot is None and "." not in number:
        return line  # bare "6 Water stains ..." — a numbered row, not a heading
    if (
        len(title) > _HEADING_MAX_LEN
        or len(title.split()) > _HEADING_MAX_WORDS
        or title.endswith(".")
    ):
        return line  # sentence-like: a list item, not a heading
    if re.search(r"\s\d{1,4}$", title):
        return line  # trailing page number: a table-of-contents entry
    depth = min(number.count(".") + 1, 4)
    return "#" * depth + " " + stripped


def _postprocess_pdf_markdown(md: str) -> str:
    """Promote numbered section titles to headings and drop repeated
    running headers/footers and standalone page numbers from PDF output."""
    if not md.strip():
        return md
    lines = md.splitlines()
    counts = Counter(
        _strip_leading_page_number(ln) for ln in lines if ln.strip()
    )
    boilerplate = {
        text
        for text, n in counts.items()
        if n >= _RUNNING_MARK_MIN_COUNT and len(text) >= _RUNNING_MARK_MIN_LEN
    }
    out: List[str] = []
    for ln in lines:
        stripped = ln.strip()
        if not stripped:
            out.append("")
            continue
        if _strip_leading_page_number(ln) in boilerplate:
            continue  # running header/footer
        if re.fullmatch(r"\d{1,3}", stripped):
            continue  # standalone page number (<=3 digits; keeps 4-digit years)
        out.append(_maybe_heading(ln))
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(out))
    return text.strip() + "\n"


_RISK_SECTION_HEADING = re.compile(r"^#{1,6}\s+(4\.\d+)\b")


def _insert_risk_tables(md: str, pdf_path: str) -> str:
    """Replace the garbled body under each risk-register subsection heading
    (## 4.1, ## 4.2, ## 4.3) with a clean Markdown table rebuilt from the PDF's
    text geometry. Only runs when the reconstruction validates against the raw
    text; otherwise the markdown is returned unchanged (see pdf_tables)."""
    from .pdf_tables import reconstruct_risk_tables

    tables = reconstruct_risk_tables(pdf_path)
    if not tables:
        return md

    lines = md.splitlines()
    out: List[str] = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        m = _RISK_SECTION_HEADING.match(line)
        if m and m.group(1) in tables:
            out.extend([line, "", tables[m.group(1)], ""])
            i += 1
            while i < n and not lines[i].lstrip().startswith("#"):
                i += 1  # drop the garbled body up to the next heading
            continue
        out.append(line)
        i += 1
    return "\n".join(out).rstrip() + "\n"


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
