"""Layout-aware reconstruction of dotted-section risk-register tables in PDFs.

MarkItDown's PDF path (pdfminer text extraction) cannot recover multi-column
table layouts: it reads each physical line left-to-right, so the two columns of
a risk register interleave word-by-word, and it sprinkles broken half-formed
Markdown table fragments through the result. The output is unreadable exactly
where a survey report is most information-dense.

This module re-reads the PDF with pdfminer's *positional* data and rebuilds
those tables from the geometry:

* a table region is a run of pages that carry the column-header labels
  ("Issue / Risk", "Recommendation", "Risk"/"Level");
* column boundaries come from clustering the body text's left edges, so no
  coordinates are hard-coded;
* rows are anchored to a consecutive item-number sequence (1, 2, 3, …) that
  runs across the "4.1 / 4.2 / 4.3" subsections;
* the item number sits a couple of points below its row's first line, so each
  anchor reclaims the out-dented opening line from the row above it.

Every step is defensive. `reconstruct_risk_tables` returns ``None`` unless the
result passes validation (consecutive numbering, a valid L/M/H level on every
row, a non-empty issue on every row, and no word gained or lost versus the raw
extracted text). When any check fails — or the geometry does not match this
family of report at all — it returns ``None`` and the caller leaves
MarkItDown's output untouched.

Scope of the guarantee, honestly: the word-multiset check catches content that
is *dropped or gained*, and the layout heuristics are tuned so that a
structural mismatch degrades to that no-op rather than a wrong table. What the
multiset check does NOT catch is content *reassigned* between rows or columns
while the overall word set stays equal. The per-row guards (non-empty issue;
strict subgroup and gutter detection) close the reassignment cases seen in
practice, but a sibling report with materially different geometry could in
principle still produce a mis-split table that validates. This runs only on
reports matching the detected structure; treat it as a strong heuristic, not a
proof of correctness.
"""

from __future__ import annotations

import collections
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# A subsection header inside the risk register: "4.1  Permits ...".
_SECTION_RE = re.compile(r"^(4\.\d+)\b")
# Column-header cell labels; their presence on a page marks it as a table page.
_HEADER_LABELS = {"Item", "no.", "Issue / Risk", "Recommendation", "Risk", "Level"}
_REQUIRED_HEADER = {"Issue / Risk", "Recommendation"}
# Organisational sub-labels that group rows within a table: exactly "External",
# or "Internal" followed by a dash ("Internal – Back of House"). Matched
# strictly so ordinary issue text starting with these words (e.g. "Internal
# partition damaged") is NOT mistaken for a group header and relocated.
_SUBGROUP_RE = re.compile(r"^External$|^Internal\s*[–—-]")
# Running header/footer text to ignore inside a table region.
_NOISE_MARKERS = ("Confidential",)
_NOISE_PREFIXES = ("Project number:",)
# A line whose top is within this many points above an item number belongs to
# that number's row (the number is typeset slightly below its first line).
_RECLAIM_TOL = 7
# Minimum points a line must extend past the recommendation column's left edge
# before we treat it as a single physical line holding both columns' text.
_STRADDLE_MARGIN = 25
_VALID_RISK = {"H", "M", "L"}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _is_noise(text: str) -> bool:
    n = _norm(text)
    return any(n.startswith(p) for p in _NOISE_PREFIXES) or any(
        m in n for m in _NOISE_MARKERS
    )


@dataclass
class _Cell:
    yg: float          # global reading-order key (top-to-bottom, across pages)
    x0: float
    x1: float
    text: str          # raw text, internal spacing preserved


@dataclass
class _Row:
    no: int
    section: str
    cells: List[_Cell] = field(default_factory=list)
    issue: str = ""
    recommendation: str = ""
    risk: str = ""
    photo: str = ""
    subgroup: str = ""   # group label that heads this row (moved from prior row)


def _extract_lines(pdf_path: str):
    """Yield (page_index, x0, x1, y0, raw_text) for every text line, or raise."""
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTTextContainer, LTTextLine

    for page_index, page in enumerate(extract_pages(pdf_path)):
        for element in page:
            if not isinstance(element, LTTextContainer):
                continue
            for line in element:
                if not isinstance(line, LTTextLine):
                    continue
                raw = line.get_text().rstrip("\n")
                if raw.strip():
                    yield (
                        page_index,
                        round(line.x0),
                        round(line.x1),
                        round(line.y0),
                        raw,
                    )


def _column_edges(x0s: List[float]) -> Optional[Tuple[float, float, float]]:
    """Left edges of the (issue, recommendation, risk) columns via 1-D
    gap clustering. Item numbers cluster with the issue text and are separated
    later by the row anchor logic, not here. Returns None if the geometry does
    not look like a three-column table."""
    xs = sorted(x0s)
    if not xs:
        return None
    clusters: List[List[float]] = [[xs[0]]]
    for x in xs[1:]:
        if x - clusters[-1][-1] > 30:
            clusters.append([x])
        else:
            clusters[-1].append(x)
    # Keep clusters with real support; tiny stray ones are extraction noise.
    edges = sorted(min(c) for c in clusters if len(c) >= 2)
    if len(edges) < 3:
        edges = sorted(min(c) for c in clusters)
    if len(edges) < 3:
        return None
    return edges[0], edges[1], edges[-1]


def _gather_table_lines(pdf_path: str):
    """Collect risk-register body lines with a global reading-order key, the
    active subsection for each, and the raw source-word multiset."""
    lines_by_page: Dict[int, list] = collections.defaultdict(list)
    for page_index, x0, x1, y0, raw in _extract_lines(pdf_path):
        lines_by_page[page_index].append((x0, x1, y0, raw))

    records: List[Tuple[str, _Cell]] = []
    source_words: "collections.Counter[str]" = collections.Counter()
    # The table region starts at the first page carrying the column headers and
    # continues over following pages (which need not repeat the headers) until
    # the next top-level section ("5 ...") begins. The active subsection and
    # item numbering carry across page breaks.
    in_region = False
    section: Optional[str] = None
    for page_index in sorted(lines_by_page):
        page = lines_by_page[page_index]
        labels = {_norm(raw) for _, _, _, raw in page}
        if not in_region:
            if not _REQUIRED_HEADER <= labels:
                continue  # table has not started yet
            in_region = True
        offset = page_index * 100000
        for x0, x1, y0, raw in sorted(page, key=lambda r: -r[2]):
            text = _norm(raw)
            if re.match(r"^5[.\s]", text) and len(text) < 70:
                in_region = False  # reached the CAPEX section; table is done
                break
            m = _SECTION_RE.match(text)
            if m and len(text) < 70:
                section = m.group(1)
                continue
            if section is None or _is_noise(text) or text in _HEADER_LABELS:
                continue
            if re.fullmatch(r"\d{1,3}", text) and y0 > 730:
                continue  # page number in the running-header band
            source_words.update(text.split())
            records.append(
                (section, _Cell(yg=offset + (1000 - y0), x0=x0, x1=x1, text=raw))
            )
        if not in_region:
            break
    return records, source_words


def _split_straddle(raw: str) -> Tuple[str, str]:
    """Split a physical line that holds both columns at its widest gutter.

    Only a run of 4+ spaces counts as a column gutter: pdfminer renders the
    inter-column gap as many spaces, whereas ordinary intra-sentence spacing is
    one or two. Requiring a wide gap avoids wrongly splitting a wide issue-only
    line that happens to contain a double space. If no such gutter exists the
    line is left whole (all issue), never guessed."""
    gaps = [(len(mo.group()), mo.start(), mo.end()) for mo in re.finditer(r"\s{4,}", raw)]
    if not gaps:
        return _norm(raw), ""
    _, start, end = max(gaps)
    return _norm(raw[:start]), _norm(raw[end:])


def _join(cells: List[Tuple[float, float, str]]) -> str:
    ordered = sorted(cells, key=lambda c: (c[0], c[1]))
    return _norm(" ".join(c[2] for c in ordered))


def _classify(row: _Row, split_ir: float, split_rr: float, l_rec: float) -> None:
    cols: Dict[str, list] = collections.defaultdict(list)
    straddle_x1 = l_rec + _STRADDLE_MARGIN
    for cell in row.cells:
        text = _norm(cell.text)
        if text.startswith("Photo"):
            cols["photo"].append((cell.yg, cell.x0, text))
        elif cell.x0 < split_ir and _SUBGROUP_RE.match(text):
            cols["subgroup"].append((cell.yg, cell.x0, text))
        elif cell.x0 >= split_rr:
            cols["risk"].append((cell.yg, cell.x0, text))
        elif cell.x0 >= split_ir:
            cols["recommendation"].append((cell.yg, cell.x0, text))
        elif cell.x1 > straddle_x1:
            issue, rec = _split_straddle(cell.text)
            if issue:
                cols["issue"].append((cell.yg, cell.x0, issue))
            if rec:
                cols["recommendation"].append((cell.yg, l_rec, rec))
        else:
            cols["issue"].append((cell.yg, cell.x0, text))
    row.issue = _join(cols["issue"])
    row.recommendation = _join(cols["recommendation"])
    row.risk = _join(cols["risk"])
    row.photo = _join(cols["photo"])
    row.subgroup = _join(cols["subgroup"])


def _build_rows(records, edges) -> List[_Row]:
    l_issue, l_rec, l_risk = edges
    split_ir = (l_issue + l_rec) / 2
    split_rr = (l_rec + l_risk) / 2
    records = sorted(records, key=lambda r: r[1].yg)

    rows: List[_Row] = []
    expected = 1
    current: Optional[_Row] = None
    pending: List[_Cell] = []
    for section, cell in records:
        text = _norm(cell.text)
        first = text.split()[0]
        is_anchor = (
            first.rstrip(".") == str(expected)
            and cell.x0 < split_ir
            and not text.startswith("Photo")
        )
        if is_anchor:
            current = _Row(no=expected, section=section)
            rows.append(current)
            expected += 1
            # Reclaim the out-dented opening line from the row just above.
            source = rows[-2].cells if len(rows) > 1 else pending
            keep, moved = [], []
            for c in source:
                (moved if cell.yg - _RECLAIM_TOL <= c.yg < cell.yg else keep).append(c)
            if len(rows) > 1:
                rows[-2].cells = keep
            else:
                pending = []
            current.cells.extend(moved)
            rest = text[len(first):].strip()
            if rest:
                current.cells.append(_Cell(cell.yg, cell.x0, cell.x1, rest))
            continue
        if current is None:
            pending.append(cell)
            continue
        current.cells.append(cell)

    for row in rows:
        _classify(row, split_ir, split_rr, l_rec)
    # A subgroup label sits in the row above the group it heads; move it down.
    for i in range(len(rows) - 1, 0, -1):
        if rows[i - 1].subgroup and not rows[i].subgroup:
            rows[i].subgroup = rows[i - 1].subgroup
            rows[i - 1].subgroup = ""
    return rows


def _validate(rows: List[_Row], source_words) -> bool:
    """Reject an implausible reconstruction. See the module docstring for the
    limits of this guard — notably it cannot see words shuffled *between* rows
    or columns, only words dropped or gained overall."""
    if not rows:
        return False
    if [r.no for r in rows] != list(range(1, len(rows) + 1)):
        return False
    if any(r.risk not in _VALID_RISK for r in rows):
        return False
    # Every risk item has an issue description; an empty issue cell means rows
    # were mis-split (a hollowed row, its content absorbed by a neighbour), so
    # discard the whole reconstruction rather than emit a corrupted table.
    if any(not row.issue.strip() for row in rows):
        return False
    out_words: "collections.Counter[str]" = collections.Counter()
    for row in rows:
        for part in (row.issue, row.recommendation, row.risk, row.photo, row.subgroup):
            out_words.update(part.split())
        # The item number was stripped from its anchor line and is re-emitted
        # as the No. column, so count it back on the output side.
        out_words.update(str(row.no).split())
    # Exact multiset equality: not one source word gained or lost.
    return out_words == source_words


def _escape(cell: str) -> str:
    return cell.replace("|", r"\|")


def render_tables(rows: List[_Row]) -> Dict[str, str]:
    """Render one Markdown table per subsection, keyed by section id ("4.1")."""
    by_section: "collections.OrderedDict[str, List[_Row]]" = collections.OrderedDict()
    for row in rows:
        by_section.setdefault(row.section, []).append(row)

    tables: Dict[str, str] = {}
    for section, section_rows in by_section.items():
        out = [
            "| No. | Issue / Risk | Recommendation | Risk | Photo |",
            "| --- | --- | --- | --- | --- |",
        ]
        for row in section_rows:
            if row.subgroup:
                out.append(f"| | **{_escape(row.subgroup)}** | | | |")
            photo = _escape(row.photo)
            out.append(
                f"| {row.no} | {_escape(row.issue)} | "
                f"{_escape(row.recommendation)} | {row.risk} | {photo} |"
            )
        tables[section] = "\n".join(out)
    return tables


def reconstruct_risk_tables(pdf_path: str) -> Optional[Dict[str, str]]:
    """Return {section_id: markdown_table} for the risk register, or None if
    the PDF has no such table or the reconstruction fails validation. Any
    unexpected error is swallowed and reported as None so callers can safely
    fall back to the unmodified conversion."""
    try:
        records, source_words = _gather_table_lines(pdf_path)
        if not records:
            return None
        edges = _column_edges([c.x0 for _, c in records])
        if edges is None:
            return None
        rows = _build_rows(records, edges)
        if not _validate(rows, source_words):
            return None
        return render_tables(rows)
    except Exception:
        return None
