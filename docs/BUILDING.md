# Building & running MDown

## Run in development (any desktop OS)

```bash
pip install -e ".[dev]"      # installs flet, markitdown + extras, pytest
flet run                     # or: python main.py
```

Hot-reload during UI work: `flet run -d` (rebuilds on file save).

## Tests

```bash
python -m pytest tests/ -q
```

To reproduce the **Android configuration** (no real magika/onnxruntime,
pure-Python converters only) in a venv:

```bash
python -m venv .venv-android && . .venv-android/bin/activate
pip install ./packaging/magika-stub "markitdown[docx,xlsx]==0.1.7" pytest
python -m pytest tests/ -q     # optional-dep tests skip themselves
```

CI runs both configurations (see `.github/workflows/ci.yml`).

## Windows build

Prerequisites: [Flutter SDK](https://docs.flutter.dev/get-started/install)
on PATH, Visual Studio with "Desktop development with C++" workload
(Flutter's Windows toolchain requirement). Then, on a Windows machine:

```powershell
pip install flet==0.28.3
flet build windows
```

Output: `build/windows/` — a self-contained folder with `mdown.exe`
(Python runtime and all dependencies bundled; nothing to install for end
users). Zip it or wrap it with an installer of your choice.

## Android build

Prerequisites: Flutter SDK **and** Android SDK/NDK (installing Android
Studio is the easiest way), plus `flet==0.28.3` installed via pip.

**Path A — default (try first):**

```bash
flet build apk
```

`flet build` bundles Python for Android via serious_python and installs
dependencies from `pyproject.toml`, using Flet's wheel index
(`pypi.flet.dev`) for native packages. If that index carries `onnxruntime`
(magika's native dependency) for your Flet version, this just works and
you get the full converter set that has Android wheels.

**Path B — pure-Python fallback (when Path A fails resolving
onnxruntime/lxml/cryptography):**

```bash
python scripts/build_android.py
```

This builds the same app with the dependency set from
`requirements-android.txt`, substituting `packaging/magika-stub` (a local
pure-Python package that satisfies markitdown's `magika~=0.6.1`
requirement) for the real magika. File-type detection falls back to
magic-byte signatures + filename extensions — conversion behavior is
otherwise identical, and the UI automatically greys out formats whose
converters aren't present. The APK lands in `dist/android/`.

Install on a device: `adb install dist/android/*.apk` (enable "install
from unknown sources"), or distribute via Play with your own signing setup
(`flet build apk` supports `--android-signing-key-store` etc.).

## Version pins, deliberately

- `flet==0.28.3` — last stable release of the classic API; 0.80+ is the
  1.0 rewrite with breaking changes (migration is a roadmap item).
- `markitdown==0.1.7` — the stub package tracks the magika version this
  release requires (`magika~=0.6.1`); bump them together.
