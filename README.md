# MDown — Anything to Markdown

A simple, cross-platform app for **Windows and Android** that converts
documents to Markdown using
[Microsoft MarkItDown](https://github.com/microsoft/markitdown) — entirely
on your device. Pick a file, get clean Markdown, preview it, copy it, or
save it. Nothing is uploaded anywhere.

**Formats:** Word (.docx) · Excel (.xlsx/.xls) · PowerPoint (.pptx) · PDF ·
HTML · CSV · JSON/XML · Outlook .msg · EPub · Jupyter notebooks · zip
archives · plain text. (PDF/PPTX need native libraries; the app greys out
anything unavailable on your device — see the
[format matrix](docs/ARCHITECTURE.md#format-support-by-platform).)

## How it works

One Python codebase, rendered by [Flet](https://flet.dev) (Flutter-based)
on both platforms. MarkItDown runs in-process; the one native obstacle to
Android (magika → onnxruntime) is solved by a pure-Python drop-in
stand-in. The full story — system map, framework decision, platform
constraints, agent roles — is in **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

## Quick start

```bash
git clone https://github.com/GreggDispenza/MDown-App && cd MDown-App
pip install -e ".[dev]"
flet run                  # desktop window
python -m pytest tests/   # test suite
```

Building the Windows .exe and the Android .apk/.aab:
**[docs/BUILDING.md](docs/BUILDING.md)**. Cutting a release
(`python scripts/release.py patch --push`) and publishing to Google Play:
**[docs/release-guide.md](docs/release-guide.md)** and the
**[Play release checklist](docs/play-release-checklist.md)**.

## Using the app

1. **Choose files** — pick one or more documents (the picker only offers
   formats supported on your device).
2. Read the result in the **Preview** tab, or grab the source from the
   **Markdown** tab.
3. **Copy** to clipboard, or **Save .md** (a file dialog on Windows; on
   Android, the app's external files folder when reachable, otherwise
   app-private storage — Copy is the reliable path there).

### PDF handling

PDF text extraction is inherently lossy, so MDown does two extra things for
PDFs beyond a plain conversion:

- **Structure clean-up** — numbered section titles (`4.1 …`) become Markdown
  headings, and repeated running headers/footers and standalone page numbers
  are dropped, so the output reads as navigable Markdown rather than a flat text
  dump.
- **Risk-register tables** — survey/inspection reports whose `4.x` sections hold
  a multi-column risk register (Issue / Recommendation / Level) get those tables
  rebuilt from the PDF's text geometry into real Markdown tables, since plain
  extraction interleaves the columns. This is a **best-effort enhancement for
  that report family**: it runs only when the document has such sections, and it
  safely falls back to the ordinary conversion whenever the reconstruction
  doesn't validate (see `mdown_app/pdf_tables.py`). Other PDFs are unaffected.

## Repository layout

| Path | What it is |
|---|---|
| `main.py`, `mdown_app/` | the app — `ui.py` (Flet UI), `engine.py` (MarkItDown wrapper), `pdf_tables.py` (risk-register table reconstruction) |
| `packaging/magika-stub/` | pure-Python magika stand-in enabling Android builds (never publish to PyPI) |
| `scripts/build_android.py` | APK/AAB build with the pure-Python dependency set |
| `scripts/release.py` | one-command version bump + tag to cut a release |
| `scripts/make_icon.py`, `make_store_assets.py` | regenerate the launcher icon and Play store graphics |
| `assets/` | launcher icon (`icon.png`) and Play store assets (`play/`) |
| `tests/` | engine + stub tests, including an Android-configuration simulation |
| `docs/` | architecture, build guide, Play release checklist, store listing, privacy policy |

## License

MIT — see [LICENSE](LICENSE). MarkItDown is © Microsoft, MIT-licensed.
`packaging/magika-stub` reimplements a minimal magika-compatible API
(magika is © Google, Apache-2.0) and exists only for local installation.
