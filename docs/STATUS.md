# Project status

A snapshot of where MDown-App stands: what is proven, what remains, and the
known issues worth tracking. See [ARCHITECTURE.md](ARCHITECTURE.md) for the
system design and [BUILDING.md](BUILDING.md) / the
[Play release checklist](play-release-checklist.md) for the release path.

## What it is

A cross-platform (**Windows + Android**) app that converts documents to
**Markdown** entirely **on-device** — one Python codebase (Flet UI wrapping
Microsoft MarkItDown), no uploads. Formats: Word, Excel, PowerPoint, PDF, HTML,
CSV, JSON/XML, Outlook `.msg`, EPub, Jupyter, zip, plain text.

## Proven in CI

All three build-workflow jobs are green (Windows, Android build, Android
on-device smoke). Each fact below is machine-verified, not assumed:

| Proof | How it is verified |
| --- | --- |
| App **boots** on Android | Emulator smoke: process alive, Python runtime + native `.so` imports load |
| App **converts** on-device | Startup self-test converts a CSV → `MDOWN_SELFTEST OK`, byte-identical to desktop |
| App id is **`app.mdown.mdown`** | Read from the built APK's badging; matches the Play `packageName` |
| **Release signing works** | `apksigner verify` hard-gate on every build (ephemeral proof key until the real key's secrets are set) |
| Windows + Android **build** | Both installers/artifacts produced on every push |

The on-device smoke test (`scripts/android_smoke.sh`) is a permanent gate: a
green run means the app booted **and** converted a document on a real emulator.

## Remaining before Play release — all owner-only

1. Set the four `ANDROID_*` keystore secrets → the proven signing path signs
   with the real upload key.
2. Set `PLAY_SERVICE_ACCOUNT_JSON` → enables the tagged Play upload.
3. Create the Google Play account + store listing (see the release checklist).

## Known issues / follow-ups

| Priority | Item | Location |
| --- | --- | --- |
| Medium | **"Save .md" on mobile** now prefers the app's *external* files dir (`Android/data/<pkg>/files`, reachable from the Files app, no permission) and is honest when it can only reach unreachable internal storage — but a fully robust save (share sheet / MediaStore Downloads) still needs a native plugin Flet 0.28.3 lacks. Copy works as the reliable path. Needs on-device UI verification. | `mdown_app/ui.py`, `mdown_app/storage.py` |
| Low | The PDF guard uses **static caps** (size + declared page count). A small crafted PDF that abuses FlateDecode streams or object graphs to burn CPU/memory is not fully covered; closing that fully needs a timeout- or memory-capped parse (e.g. a worker subprocess), a larger change deferred for now. | `mdown_app/engine.py` |
| Low | Availability chips mark some built-in formats (EPub, JSON/XML, zip, Jupyter) always-available; conversion can still fail at runtime for edge cases. | `mdown_app/engine.py` |

## Recently addressed

- **Decided the PDF risk-register reconstruction: keep and document.** It is
  tested and safely no-ops on non-matching PDFs, so it stays; the gap was that
  it was undocumented in the app's general scope. README's "Using the app" now
  has a **PDF handling** section describing both the structure clean-up and the
  best-effort risk-register tables (and their safe fallback).
- Added a **PDF resource-exhaustion guard** (`_guard_pdf`): rejects an oversized
  file (>200 MB) or an absurd declared page count (>10,000) before pdfminer
  parses it, closing the denial-of-service gap that the archive bomb-guard never
  covered (PDFs are not zip containers). Both limits are read cheaply — a
  `stat()` and the page tree's `/Count`, without walking pages. Static caps only:
  a small file weaponising FlateDecode streams to burn CPU still needs a
  timeout/memory-capped parse, tracked below.
- PDF conversions no longer pay for a second full PDF parse unless the document
  actually has a `4.x` section heading to splice a table into.
- Corrected the archive bomb-guard docstring to describe the one bounded case
  where a nested archive member is read.
