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
from unknown sources").

## Publishing to Google Play (signed AAB)

Google Play requires a **release-signed App Bundle (`.aab`)**, not an APK.
Both `flet build` and `scripts/build_android.py` accept `aab` as the target:

```bash
flet build aab                       # or: python scripts/build_android.py aab
```

### One-time: create an upload keystore

Keep this file forever — losing it means you can no longer update the app.

```bash
keytool -genkey -v -keystore upload-keystore.jks \
  -keyalg RSA -keysize 2048 -validity 10000 -alias upload
```

### Sign a local build

```bash
flet build aab \
  --android-signing-key-store upload-keystore.jks \
  --android-signing-key-store-password "$KS_PW" \
  --android-signing-key-password "$KEY_PW" \
  --android-signing-key-alias upload \
  --build-number 1 --build-version 0.1.0
```

`--build-number` is the integer **versionCode** (must increase on every
upload); `--build-version` is the **versionName**. Enrol the app in **Play
App Signing**: you upload signed with this *upload* key and Google re-signs
with the managed *app signing* key.

### CI signing (GitHub Actions)

The `android` job in `.github/workflows/build.yml` builds both an `.apk`
(sideload/QA) and an `.aab` (Play). It signs with your **real upload key**
when these repository **secrets** are present; when they are absent it signs
with a throwaway **ephemeral proof key** generated in the job (and prints a
warning) so the signing path is exercised and verified on every build — an
`apksigner verify` step is a hard gate. An ephemeral-signed build is fine for
sideload/QA but is **not** uploadable to Play (the Play-upload step requires the
real `ANDROID_KEYSTORE_B64` secret). Supply these to sign a real release:

| Secret | Value |
| --- | --- |
| `ANDROID_KEYSTORE_B64` | `base64 -w0 upload-keystore.jks` output |
| `ANDROID_KEYSTORE_PASSWORD` | keystore password |
| `ANDROID_KEY_PASSWORD` | key password |
| `ANDROID_KEY_ALIAS` | `upload` |

The versionCode is the CI run number (`github.run_number`), so every build
is uniquely, monotonically numbered. Artifacts: `mdown-android-aab` (upload
this to Play) and `mdown-android` (APK for sideloading).

### App icon

`assets/icon.png` (1024×1024) is the launcher icon; `flet build` derives
every Android density and the adaptive-icon foreground from it. Regenerate
it with `python scripts/make_icon.py`. The CI build passes a matching
`--android-adaptive-icon-background`.

## Version pins, deliberately

- `flet==0.28.3` — last stable release of the classic API; 0.80+ is the
  1.0 rewrite with breaking changes (migration is a roadmap item).
- `markitdown==0.1.7` — the stub package tracks the magika version this
  release requires (`magika~=0.6.1`); bump them together.
