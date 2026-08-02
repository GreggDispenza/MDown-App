#!/usr/bin/env bash
# On-device smoke test, run INSIDE the booted emulator by the android-smoke job
# (.github/workflows/build.yml). It proves two things on a real device:
#   1. the app launches and its Python runtime starts (process alive + Python/UI
#      visible in logcat), and
#   2. a real conversion runs on-device and produces correct Markdown — the app
#      self-tests when asked (a debug system property) and writes a verdict to
#      its external files dir, which adb reads back here.
#
# The result is carried by this script's exit code (a job conclusion is readable
# via the API; the emulator's logcat/screenshots are not). Job logs are read
# tail-truncated, so a compact SUMMARY is printed LAST.
#
# Package name and launchable activity are DISCOVERED from the APK via aapt
# badging (flet's applicationId, e.g. app.mdown.mdown_app, is derived from
# pyproject [project].name and is not obvious).
set -uo pipefail

apk="$(ls apk/*.apk 2>/dev/null | head -1)"
abis="$(unzip -l "$apk" 2>/dev/null | grep -oE 'lib/[^/]+' | sort -u | tr '\n' ' ')"

sdk="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-}}"
badging=""
for t in $(find "$sdk/build-tools" \( -name aapt -o -name aapt2 \) 2>/dev/null | sort -V -r); do
  badging="$("$t" dump badging "$apk" 2>/dev/null)" && [ -n "$badging" ] && break || true
done
PKG="$(printf '%s\n' "$badging" | sed -n "s/^package: name='\([^']*\)'.*/\1/p" | head -1)"
ACT="$(printf '%s\n' "$badging" | sed -n "s/^launchable-activity: name='\([^']*\)'.*/\1/p" | head -1)"

adb wait-for-device
for _ in $(seq 1 60); do
  [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ] && break
  sleep 2
done
adb logcat -c || true

# Ask the app to run its on-device conversion self-test at startup.
adb shell setprop debug.mdown_selftest 1 || true

install_out="$(adb install -r "$apk" 2>&1 | tail -3)"
if [ -n "$PKG" ] && [ -n "$ACT" ]; then
  amstart_out="$(adb shell am start -W -n "$PKG/$ACT" 2>&1 | tail -4)"
elif [ -n "$PKG" ]; then
  amstart_out="$(adb shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 2>&1 | tail -4)"
else
  amstart_out="(no package discovered from APK)"
fi

read_result() {  # echo the self-test verdict line, trying adb-readable locations
  local p="/storage/emulated/0/Android/data/$PKG/files/mdown_selftest.txt" out
  out="$(adb shell "cat '$p'" 2>/dev/null | tr -d '\r' | grep -m1 MDOWN_SELFTEST)"
  [ -n "$out" ] && { echo "$out"; return; }
  out="$(adb exec-out run-as "$PKG" cat files/mdown_selftest.txt 2>/dev/null | tr -d '\r' | grep -m1 MDOWN_SELFTEST)"
  [ -n "$out" ] && { echo "$out"; return; }
}

# Poll up to ~120s — serious_python unpacks the interpreter, then self-tests.
pid=""; signal=""; result=""
for _ in $(seq 1 40); do
  sleep 3
  [ -n "$PKG" ] && pid="$(adb shell pidof "$PKG" 2>/dev/null | tr -d '\r')"
  signal="$(adb logcat -d 2>/dev/null | grep -m1 -E "$PKG.*(python_bundle|python_site_packages|MainActivity)|Displayed.*$PKG" || true)"
  [ -z "$result" ] && [ -n "$PKG" ] && result="$(read_result)"
  [ -n "$pid" ] && [ -n "$signal" ] && [ -n "$result" ] && break
done

crash="$(adb logcat -d 2>/dev/null \
  | grep -iE "${PKG:-app.mdown}|python|flet|serious|dlopen|UnsatisfiedLink|AndroidRuntime|FATAL|E DEBUG" \
  | tail -20)"

reason="OK"
if [ -z "$apk" ]; then reason="no APK under apk/"
elif [ -z "$PKG" ]; then reason="could not read package name from APK (aapt badging failed)"
elif [ -z "$pid" ]; then reason="app process not alive after launch (startup crash?)"
elif [ -z "$signal" ]; then reason="no evidence of the app's Python/UI running in logcat"
elif [ -z "$result" ]; then reason="on-device self-test verdict not found (conversion did not run, or file unreadable)"
elif ! printf '%s' "$result" | grep -q 'MDOWN_SELFTEST OK'; then reason="on-device conversion FAILED: $result"
fi

echo "================ SMOKE SUMMARY ================"
echo "apk          = $apk"
echo "abis         = ${abis:-<none>}"
echo "package      = ${PKG:-<unknown>}"
echo "activity     = ${ACT:-<unknown>}"
echo "install      : $install_out"
echo "am start     : $amstart_out"
echo "pid          = '$pid'"
echo "alive signal = '$signal'"
echo "self-test    = '${result:-<no verdict file>}'"
echo "---- relevant logcat (tail) ----"
echo "${crash:-<no matching logcat lines>}"
echo "RESULT       : $reason"
[ "$reason" = "OK" ] || { echo "::error::smoke failed: $reason"; exit 1; }
echo "SMOKE PASS: app booted AND converted a document on-device (pid $pid; $result)"
