"""Tests for the risk-register table reconstruction (mdown_app.pdf_tables).

The real report PDF is not committed, so these exercise the geometry, row
grouping, validation and rendering with synthetic positioned cells that mirror
the two-column layout, plus the engine splice with a stubbed reconstructor.
"""

import mdown_app.engine as engine
from mdown_app.pdf_tables import (
    _Cell,
    _build_rows,
    _column_edges,
    _split_straddle,
    _validate,
    render_tables,
    reconstruct_risk_tables,
)

# Column left edges: item numbers cluster with the issue text at ~117.
EDGES = (117, 303, 518)


def _cell(yg, x0, text, x1=None):
    return _Cell(yg=yg, x0=x0, x1=x1 if x1 is not None else x0 + 40, text=text)


def test_column_edges_clusters_three_columns():
    xs = [92, 92, 117, 117, 117, 303, 303, 388, 508, 518, 518]
    assert _column_edges(xs) == (92, 303, 508)


def test_column_edges_rejects_non_tabular_geometry():
    assert _column_edges([100, 101, 102]) is None
    assert _column_edges([]) is None


def test_split_straddle_breaks_on_widest_gutter():
    issue, rec = _split_straddle("Cracks observed at ceiling      Repair and repaint.")
    assert issue == "Cracks observed at ceiling"
    assert rec == "Repair and repaint."


def test_build_rows_separates_columns_and_reclaims_first_line():
    # Row 1's opening issue line sits 2pt above its item number (out-dented);
    # the anchor must reclaim it. A separate rec cell shares the top line's y.
    records = [
        ("4.1", _cell(0, 117, "Name on the sign")),        # issue, above number
        ("4.1", _cell(0, 303, "Replace the name", x1=470)),  # rec, top line
        ("4.1", _cell(2, 92, "1", x1=100)),                 # item-number anchor
        ("4.1", _cell(4, 518, "L", x1=527)),                # risk
        ("4.1", _cell(17, 117, "is Mojo Nomad.")),          # issue, wrapped
        ("4.1", _cell(34, 303, "Photo: D1", x1=350)),       # photo
        # Row 2 uses an embedded number ("2 ...") like the real §4.2 layout.
        ("4.1", _cell(60, 92, "2  Broken tile here", x1=290)),
        ("4.1", _cell(60, 303, "Fix the tile", x1=470)),
        ("4.1", _cell(64, 518, "M", x1=527)),
    ]
    rows = _build_rows(records, EDGES)
    assert [r.no for r in rows] == [1, 2]
    r1, r2 = rows
    assert r1.issue == "Name on the sign is Mojo Nomad."
    assert r1.recommendation == "Replace the name"
    assert r1.risk == "L"
    assert r1.photo == "Photo: D1"
    assert r2.issue == "Broken tile here"      # embedded number stripped
    assert r2.recommendation == "Fix the tile"
    assert r2.risk == "M"


def test_build_rows_moves_subgroup_label_to_following_row():
    records = [
        ("4.2", _cell(0, 92, "1  First issue", x1=290)),
        ("4.2", _cell(0, 303, "First rec", x1=470)),
        ("4.2", _cell(4, 518, "L", x1=527)),
        ("4.2", _cell(30, 83, "Internal – Back of House")),  # group label
        ("4.2", _cell(60, 92, "2  Second issue", x1=290)),
        ("4.2", _cell(60, 303, "Second rec", x1=470)),
        ("4.2", _cell(64, 518, "L", x1=527)),
    ]
    rows = _build_rows(records, EDGES)
    assert rows[0].subgroup == ""
    assert rows[1].subgroup == "Internal – Back of House"  # heads the next row


def _good_rows():
    records = [
        ("4.1", _cell(2, 92, "1  Alpha issue", x1=290)),
        ("4.1", _cell(2, 303, "Alpha fix", x1=470)),
        ("4.1", _cell(4, 518, "L", x1=527)),
        ("4.1", _cell(60, 92, "2  Beta issue", x1=290)),
        ("4.1", _cell(60, 303, "Beta fix", x1=470)),
        ("4.1", _cell(64, 518, "M", x1=527)),
    ]
    import collections
    words = collections.Counter()
    for _, c in records:
        words.update(c.text.split())
    return _build_rows(records, EDGES), words


def test_validate_accepts_clean_reconstruction():
    rows, words = _good_rows()
    assert _validate(rows, words) is True


def test_validate_rejects_lost_word():
    rows, words = _good_rows()
    words["Ghost"] += 1  # a source word that never made it into the output
    assert _validate(rows, words) is False


def test_validate_rejects_bad_risk_level():
    rows, words = _good_rows()
    rows[0].risk = "X"
    assert _validate(rows, words) is False


def test_validate_rejects_non_consecutive_numbering():
    rows, words = _good_rows()
    rows[1].no = 3
    assert _validate(rows, words) is False


def test_render_tables_emits_header_and_subgroup_rows():
    rows, _ = _good_rows()
    rows[1].subgroup = "External"
    tables = render_tables(rows)
    tbl = tables["4.1"]
    assert tbl.splitlines()[0] == "| No. | Issue / Risk | Recommendation | Risk | Photo |"
    assert "| | **External** | | | |" in tbl
    assert "| 1 | Alpha issue | Alpha fix | L |" in tbl


def test_render_tables_escapes_pipes():
    rows, _ = _good_rows()
    rows[0].issue = "a | b"
    tbl = render_tables(rows)["4.1"]
    assert r"a \| b" in tbl


def test_reconstruct_returns_none_on_missing_file():
    assert reconstruct_risk_tables("/no/such/file.pdf") is None


# ---- engine splice --------------------------------------------------------

def test_insert_risk_tables_replaces_garbled_body(monkeypatch):
    md = "\n".join([
        "# 4.  Defect, Risk Overview and Recommendations",
        "",
        "Intro paragraph about High, Medium, Low.",
        "",
        "## 4.1  Permits and Approvals",
        "| Item | | garbled | table | fragment |",
        "some scrambled column text",
        "## 4.2  Building Structure",
        "more garbled rows",
        "# 5. CAPEX Estimate",
        "The CAPEX total is 606,150.00.",
    ])
    fake = {
        "4.1": "| No. | Issue / Risk | Recommendation | Risk | Photo |\n| --- | --- | --- | --- | --- |\n| 1 | X | Y | L |  |",
        "4.2": "| No. | Issue / Risk | Recommendation | Risk | Photo |\n| --- | --- | --- | --- | --- |\n| 6 | P | Q | M |  |",
    }
    monkeypatch.setattr(
        "mdown_app.pdf_tables.reconstruct_risk_tables", lambda p: fake
    )
    out = engine._insert_risk_tables(md, "dummy.pdf")
    # Clean tables spliced in; garbled fragments gone; surrounding text kept.
    assert "| 1 | X | Y | L |" in out
    assert "| 6 | P | Q | M |" in out
    assert "garbled" not in out and "scrambled" not in out
    assert "Intro paragraph about High, Medium, Low." in out
    assert "The CAPEX total is 606,150.00." in out
    assert "## 4.1  Permits and Approvals" in out


def test_insert_risk_tables_noop_when_reconstruction_fails(monkeypatch):
    md = "## 4.1  Permits\n| garbled |\nbody\n# 5. Next\n"
    monkeypatch.setattr(
        "mdown_app.pdf_tables.reconstruct_risk_tables", lambda p: None
    )
    assert engine._insert_risk_tables(md, "dummy.pdf") == md
