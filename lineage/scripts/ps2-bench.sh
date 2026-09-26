#!/system/bin/sh
# PS2 benchmark on the v2 box (run with `adb shell sh /data/local/tmp/ps2-bench.sh [seconds] [iso]`):
# starts a game in ARMSX2 the way Pegasus does (BootSplashActivity + SAF tree content:// URI), collects
# ARMSX2's PerfLog lines (fps, EE/GS/VU thread load), CPU/GPU clocks and temperatures, then leaves.
SECS=${1:-70}
ISO=${2:-God of War (Europe, Australia) (En,Fr,De,Es,It).iso}
enc() { printf '%s' "$1" | sed 's/%/%25/g; s/ /%20/g; s/(/%28/g; s/)/%29/g; s/,/%2C/g; s/:/%3A/g; s#/#%2F#g; s/&/%26/g'; }
URI="content://com.android.externalstorage.documents/tree/primary%3AROMs%2Fps2/document/$(enc "primary:ROMs/ps2/$ISO")"
input keyevent KEYCODE_HOME
sleep 2
logcat -c
am start -n com.armsx2/com.armsx2.BootSplashActivity -a android.intent.action.VIEW -d "$URI" >/dev/null
T0=$(date +%s)
while [ $(( $(date +%s) - T0 )) -lt "$SECS" ]; do
    sleep 10
    t=""; for z in /sys/class/thermal/thermal_zone*/temp; do t="$t $(( $(cat $z) / 1000 ))"; done
    echo "t+$(( $(date +%s) - T0 ))s cpu0=$(( $(cat /sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq) / 1000 )) cpu2=$(( $(cat /sys/devices/system/cpu/cpufreq/policy2/scaling_cur_freq) / 1000 )) gpu=$(( $(cat /sys/class/devfreq/ffe40000.bifrost/cur_freq) / 1000000 )) temp=$t"
done
logcat -d | grep -o "PerfLog: .*" | tail -8
input keyevent KEYCODE_HOME
sleep 3
am force-stop com.armsx2
