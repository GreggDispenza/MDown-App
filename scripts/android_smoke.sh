#!/usr/bin/env bash
# On-device smoke test, run INSIDE the booted emulator by the android-smoke job
# (.github/workflows/build.yml). Proves the biggest unknown: that the app
# launches and its Python runtime starts on Android.
#
# The result is carried by this script's exit code (a job conclusion is
# readable via the API; the emulator's logcat/screenshots are artifacts this
# environment cannot download). Job logs are read tail-truncated, so a compact
# SUMMARY is printed LAST — package/activity, install/launch output, pid, boot
# marker, relevant crash logcat, and the verdict on the final line.
#
# The package name and launchable activity are DISCOVERED from the APK via
# aapt badging, not hard-coded: flet derives the Android applicationId from
# pyproject [project].name (mdown-app -> app.mdown.mdown_app), which is not
# obvious, so reading it from the artifact is the only reliable source.
set -uo pipefail

apk="$(ls apk/*.apk 2>/dev/null | head -1)"
abis="$(unzip -l "$apk" 2>/dev/null | grep -oE 'lib/[^/]+' | sort -u | tr '\n' ' ')"

# Discover package + launchable activity from the APK (ground truth).
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

install_out="$(adb install -r "$apk" 2>&1 | tail -3)"
if [ -n "$PKG" ] && [ -n "$ACT" ]; then
  amstart_out="$(adb shell am start -W -n "$PKG/$ACT" 2>&1 | tail -4)"
elif [ -n "$PKG" ]; then
  amstart_out="$(adb shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 2>&1 | tail -4)"
else
  amstart_out="(no package discovered from APK)"
fi

# Poll up to ~90s — serious_python unpacks the interpreter on first launch.
pid=""; marker=""
for _ in $(seq 1 30); do
  sleep 3
  [ -n "$PKG" ] && pid="$(adb shell pidof "$PKG" 2>/dev/null | tr -d '\r')"
  marker="$(adb logcat -d 2>/dev/null | grep -m1 'MDOWN_BOOT_PROBE' || true)"
  [ -n "$pid" ] && [ -n "$marker" ] && break
done

crash="$(adb logcat -d 2>/dev/null \
  | grep -iE "${PKG:-app.mdown}|python|flet|serious|dlopen|UnsatisfiedLink|AndroidRuntime|FATAL|E DEBUG" \
  | tail -25)"

reason="OK"
if [ -z "$apk" ]; then reason="no APK under apk/"
elif [ -z "$PKG" ]; then reason="could not read package name from APK (aapt badging failed)"
elif [ -z "$pid" ]; then reason="app process not alive after launch (startup crash?)"
elif [ -z "$marker" ]; then reason="boot marker not in logcat (Python did not reach startup, or stdout not routed)"
fi

echo "================ SMOKE SUMMARY ================"
echo "apk       = $apk"
echo "abis      = ${abis:-<none>}"
echo "package   = ${PKG:-<unknown>}"
echo "activity  = ${ACT:-<unknown>}"
echo "install   : $install_out"
echo "am start  : $amstart_out"
echo "pid       = '$pid'"
echo "marker    = '$marker'"
echo "---- relevant logcat (tail) ----"
echo "${crash:-<no matching logcat lines>}"
echo "RESULT    : $reason"
[ "$reason" = "OK" ] || { echo "::error::smoke failed: $reason"; exit 1; }
echo "SMOKE PASS: app booted and the Python runtime ran (package $PKG)"
