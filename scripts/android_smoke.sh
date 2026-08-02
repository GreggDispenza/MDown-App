#!/usr/bin/env bash
# On-device smoke test, run INSIDE the booted emulator by the android-smoke job
# (.github/workflows/build.yml). Proves the biggest unknown: that the app
# launches and its Python runtime starts on Android.
#
# The result is carried by this script's exit code (a job conclusion is
# readable via the API; the emulator's logcat/screenshots are artifacts this
# environment cannot download). Because job logs are read tail-truncated, the
# script prints a compact SUMMARY *last* so a failure is fully diagnosable from
# the tail: APK ABIs, install/launch output, pid, boot marker, and the relevant
# crash lines, with the verdict on the final line.
#
# Ground truth (not guessed): launch component app.mdown.mdown/.MainActivity,
# from the flet 0.28.3 build template.
set -uo pipefail

PKG="app.mdown.mdown"
COMPONENT="$PKG/.MainActivity"
apk="$(ls apk/*.apk 2>/dev/null | head -1)"

abis="$(unzip -l "$apk" 2>/dev/null | grep -oE 'lib/[^/]+' | sort -u | tr '\n' ' ')"

adb wait-for-device
# Wait for full boot (sys.boot_completed) — up to ~120s — before installing.
for _ in $(seq 1 60); do
  [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ] && break
  sleep 2
done
adb logcat -c || true

install_out="$(adb install -r "$apk" 2>&1 | tail -3)"
amstart_out="$(adb shell am start -W -n "$COMPONENT" 2>&1 | tail -4)"

# Poll up to ~90s — serious_python unpacks the interpreter on first launch.
pid=""; marker=""
for _ in $(seq 1 30); do
  sleep 3
  pid="$(adb shell pidof "$PKG" 2>/dev/null | tr -d '\r')"
  marker="$(adb logcat -d 2>/dev/null | grep -m1 'MDOWN_BOOT_PROBE' || true)"
  [ -n "$pid" ] && [ -n "$marker" ] && break
done

crash="$(adb logcat -d 2>/dev/null \
  | grep -iE "$PKG|python|flet|serious|dlopen|UnsatisfiedLink|couldn't find|AndroidRuntime|FATAL|E DEBUG" \
  | tail -25)"

reason="OK"
if [ -z "$apk" ]; then reason="no APK under apk/"
elif [ -z "$pid" ]; then reason="app process not alive after launch (startup crash?)"
elif [ -z "$marker" ]; then reason="boot marker not in logcat (Python did not reach startup, or stdout not routed)"
fi

echo "================ SMOKE SUMMARY ================"
echo "apk       = $apk"
echo "abis      = ${abis:-<none>}"
echo "install   : $install_out"
echo "am start  : $amstart_out"
echo "pid       = '$pid'"
echo "marker    = '$marker'"
echo "---- relevant logcat (tail) ----"
echo "${crash:-<no matching logcat lines>}"
echo "RESULT    : $reason"
[ "$reason" = "OK" ] || { echo "::error::smoke failed: $reason"; exit 1; }
echo "SMOKE PASS: app booted and the Python runtime ran"
