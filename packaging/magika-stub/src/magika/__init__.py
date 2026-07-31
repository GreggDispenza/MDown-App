"""Pure-Python stand-in for Google's `magika` content-type detector.

Why this exists
---------------
`markitdown` hard-depends on `magika ~= 0.6.1`, and real magika depends on
`onnxruntime` — a native library with no wheels for some targets we care
about (notably Android, where Flet/serious_python installs packages for an
ARM Python it cross-builds). This package has the *same distribution name
and version* as real magika, so installing it from a local path satisfies
markitdown's requirement without pulling in onnxruntime.

It implements the small slice of the magika API that markitdown actually
uses (`Magika().identify_stream(...)` / `identify_bytes(...)` returning an
object with `.status` and `.prediction.output.{label,mime_type,is_text,
extensions}`), backed by magic-byte signatures instead of a neural model.
When it cannot tell what a file is it reports "unknown", which makes
markitdown fall back to filename-extension/mimetype guessing — exactly the
information the MDown app always has, because files arrive via a picker.

MUST NEVER be published to a package index. Install only from this
repository path (see requirements-android.txt / docs/BUILDING.md).
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from typing import BinaryIO, List

__version__ = "0.6.1"

# How much of the stream we read for sniffing. Office zip archives keep
# their telltale member names in the central directory, so we read enough
# to let zipfile parse small files outright and fall back to header-only
# checks for larger ones.
_SNIFF_BYTES = 1 << 20  # 1 MiB


@dataclass
class ContentTypeInfo:
    label: str = "unknown"
    mime_type: str = "application/octet-stream"
    is_text: bool = False
    extensions: List[str] = field(default_factory=list)
    description: str = ""


@dataclass
class MagikaPrediction:
    output: ContentTypeInfo = field(default_factory=ContentTypeInfo)
    score: float = 1.0


@dataclass
class MagikaResult:
    status: str = "ok"
    prediction: MagikaPrediction = field(default_factory=MagikaPrediction)

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def _info(label: str, mime: str, is_text: bool, *exts: str) -> ContentTypeInfo:
    return ContentTypeInfo(
        label=label, mime_type=mime, is_text=is_text, extensions=list(exts)
    )


def _detect_zip(data: bytes) -> ContentTypeInfo:
    """Distinguish OOXML/epub containers from plain zip via member names."""
    try:
        names = zipfile.ZipFile(BytesIO(data)).namelist()
    except Exception:
        # Truncated central directory (file larger than our sniff window):
        # all we can say is "it's zip-like"; report unknown so markitdown
        # trusts the filename extension instead.
        return ContentTypeInfo()
    joined = " ".join(names)
    if "word/" in joined:
        return _info(
            "docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            False,
            "docx",
        )
    if "xl/" in joined:
        return _info(
            "xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            False,
            "xlsx",
        )
    if "ppt/" in joined:
        return _info(
            "pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            False,
            "pptx",
        )
    if "mimetype" in names and b"epub" in data[:200]:
        return _info("epub", "application/epub+zip", False, "epub")
    return _info("zip", "application/zip", False, "zip")


def _looks_like_text(data: bytes) -> bool:
    if not data:
        return False
    sample = data[:4096]
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
        return True
    except UnicodeDecodeError:
        # Not UTF-8; could still be a legacy 8-bit text encoding. Count
        # bytes that are printable in common single-byte encodings.
        printable = sum(1 for b in sample if 32 <= b < 127 or b in (9, 10, 13))
        return printable / len(sample) > 0.95


def _detect(data: bytes) -> ContentTypeInfo:
    if data.startswith(b"%PDF-"):
        return _info("pdf", "application/pdf", False, "pdf")
    if data.startswith(b"PK\x03\x04"):
        return _detect_zip(data)
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return _info("png", "image/png", False, "png")
    if data.startswith(b"\xff\xd8\xff"):
        return _info("jpeg", "image/jpeg", False, "jpg", "jpeg")
    if data.startswith((b"GIF87a", b"GIF89a")):
        return _info("gif", "image/gif", False, "gif")
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return _info("webp", "image/webp", False, "webp")
    if _looks_like_text(data):
        head = data[:2048].lstrip().lower()
        if head.startswith((b"<!doctype html", b"<html")):
            return _info("html", "text/html", True, "html", "htm")
        if head.startswith(b"<?xml"):
            return _info("xml", "text/xml", True, "xml")
        # Generic text: report "unknown" rather than guessing txt/csv/json
        # apart, so markitdown prefers the filename extension. ("unknown"
        # with is_text=False is how real magika behaves on empty input too.)
        return ContentTypeInfo()
    return ContentTypeInfo()


class Magika:
    """API-compatible subset of magika.Magika (signature-based)."""

    def __init__(self, *args, **kwargs) -> None:  # signature-compatible
        pass

    def identify_bytes(self, data: bytes) -> MagikaResult:
        return MagikaResult(prediction=MagikaPrediction(output=_detect(data)))

    def identify_stream(self, stream: BinaryIO) -> MagikaResult:
        pos = stream.tell()
        try:
            data = stream.read(_SNIFF_BYTES)
        finally:
            stream.seek(pos)
        return self.identify_bytes(data)

    def identify_path(self, path) -> MagikaResult:
        with open(path, "rb") as f:
            return self.identify_stream(f)


__all__ = [
    "Magika",
    "MagikaResult",
    "MagikaPrediction",
    "ContentTypeInfo",
    "__version__",
]
