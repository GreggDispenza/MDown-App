#!/usr/bin/env bash
# On-device smoke test, run INSIDE the booted emulator by the android-smoke job
# (.github/workflows/build.yml). It proves the single biggest unknown: that the
# app launches and its Python runtime actually starts on Android.
#
# Signal design: the emulator's logcat and screenshots are artifacts this
# environment's proxy cannot download, but a job's pass/fail conclusion IS
# readable via the API. So this script encodes the result purely in its exit
# code — 0 only when the app is alive AND our Python boot marker reached logcat.
#
# Ground-truth values (not guesses): the launchable component is
# app.mdown.mdown/.MainActivity, read from the flet 0.28.3 build template.
set -uo pipefail

PKG="app.mdown.mdown"
COMPONENT="$PKG/.MainActivity"
apk="$(ls apk/*.apk 2>/dev/null | head -1)"

fail() {
  echo "::error::$1"
  echo "---- last 120 logcat lines ----"
  adb logcat -d 2>/dev/null | tail -120
  exit 1
}

[ -n "$apk" ] || fail "no APK found under apk/"
echo "APK: $apk ($(stat -c%s "$apk" 2>/dev/null || echo '?') bytes)"

adb wait-for-device
adb logcat -c || true
adb install -r -g "$apk" || fail "adb install failed"
adb shell am start -W -n "$COMPONENT" || fail "am start failed for $COMPONENT"

# Poll up to ~90s — serious_python unpacks the interpreter on first launch.
pid=""; marker=""
for _ in $(seq 1 30); do
  sleep 3
  pid="$(adb shell pidof "$PKG" 2>/dev/null | tr -d '\r')"
  marker="$(adb logcat -d 2>/dev/null | grep -m1 'MDOWN_BOOT_PROBE' || true)"
  [ -n "$pid" ] && [ -n "$marker" ] && break
done

echo "pid='$pid'  marker='$marker'"
adb logcat -d 2>/dev/null | grep -iE "python|flet|serious|AndroidRuntime|FATAL" | tail -60 || true

[ -n "$pid" ] || fail "app process not alive after launch (startup crash?)"
echo "LIVENESS: app process alive (pid $pid)"
[ -n "$marker" ] || fail "boot marker not in logcat (Python did not reach startup, or stdout not routed to logcat)"
echo "SMOKE PASS: app booted and the Python runtime ran ($marker)"
