#!/usr/bin/env bash
# Smoke test of the modded box. Run while the home screen is in the foreground. Prints OK/FAIL per check; exit 1 if any FAIL.
source "$(dirname "$0")/lib.sh"
require_device
FAILS=0
check() { local name="$1" got="$2" want="$3"; if [ "$got" = "$want" ]; then echo "OK   $name = $got"; else echo "FAIL $name = '$got' (want '$want')"; FAILS=$((FAILS+1)); fi; }
contains() { local name="$1" hay="$2" needle="$3"; case "$hay" in *"$needle"*) echo "OK   $name";; *) echo "FAIL $name (missing $needle)"; FAILS=$((FAILS+1));; esac; }

check "release"        "$(ash getprop ro.build.version.release)" "14"
check "sdk"            "$(ash getprop ro.build.version.sdk)" "28"
check "model"          "$(ash getprop ro.product.model)" "GTKing PRO"
contains "overlays"    "$(ash 'ls -1 /data/local/gtk-backup 2>/dev/null')" "gtk-identity"
check "root"           "$(ash id -u)" "0"
check "system ro"      "$(ash "mount | grep ' / ' | grep -c '(ro'")" "1"
contains "home"        "$(ash 'dumpsys activity activities | grep mResumedActivity')" "$(ash 'cmd package query-activities --brief -a android.intent.action.MAIN -c android.intent.category.HOME' | grep -vE 'tvlauncher|FallbackHome' | grep -oE '[a-z][a-z0-9_.]+/' | head -1)"
contains "gms"         "$(ash 'pm list packages')" "com.google.android.gms"
contains "kodi"        "$(ash 'pm list packages')" "org.xbmc.kodi"
echo "info hosts lines = $(ash 'wc -l < /system/etc/hosts')"
contains "hdmi 4k60"   "$(ash 'cat /sys/class/amhdmitx/amhdmitx0/disp_cap')" "2160p60hz"
contains "hdmi dts-hd" "$(ash 'cat /sys/class/amhdmitx/amhdmitx0/aud_cap')" "DTS-HD"
echo "disabled: $(ash 'pm list packages -d' | wc -l | tr -d ' ') packages"
[ "$FAILS" = 0 ] && { echo "ALL OK"; exit 0; } || { echo "$FAILS FAIL(s)"; exit 1; }
