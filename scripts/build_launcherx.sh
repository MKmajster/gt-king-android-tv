#!/usr/bin/env bash
# Assemble overlays/gtk-launcherx (Google TV Home as /system/priv-app) from the Google-signed APK in apps/launcherx/.
# System apps get no native-lib extraction by PackageManager, so lib/armeabi-v7a/*.so are unpacked to lib/arm/ next to the APK.
# Usage: scripts/build_launcherx.sh [path/to/launcherx.apk]   (default: newest apps/launcherx/com.google.android.apps.tv.launcherx_*.apk)
source "$(dirname "$0")/lib.sh"

APK="${1:-$(ls -1 "$REPO_ROOT"/apps/launcherx/com.google.android.apps.tv.launcherx_*.apk 2>/dev/null | sort | tail -1)}"
[ -f "$APK" ] || die "no LauncherX APK — put com.google.android.apps.tv.launcherx_<ver>.apk in apps/launcherx/ (last Android 9 build: 1.0.436578635)"
AAPT="$HOME/Library/Android/sdk/build-tools/37.0.0/aapt"
[ -x "$AAPT" ] || die "aapt not found at $AAPT"
min="$("$AAPT" dump badging "$APK" 2>/dev/null | grep -oE "sdkVersion:'[0-9]+'" | grep -oE '[0-9]+' || true)"
[ "${min:-99}" -le 28 ] || die "$(basename "$APK") needs SDK ${min:-?} > 28"

DST="$REPO_ROOT/overlays/gtk-launcherx/system/priv-app/GoogleTVHome"
rm -rf "$DST"; mkdir -p "$DST/lib/arm"
cp "$APK" "$DST/GoogleTVHome.apk"
unzip -q -o -j "$APK" 'lib/armeabi-v7a/*.so' -d "$DST/lib/arm" || die "no armeabi-v7a libs in APK"
log "overlay gtk-launcherx built: $(ls "$DST/lib/arm" | wc -l | tr -d ' ') native lib(s)"
ls -la "$DST" "$DST/lib/arm"
