#!/usr/bin/env bash
# Post-flash functional check of LineageOS 22.2 on the Beelink GT-King (galilei), over adb (WiFi).
#   bash lineage/scripts/postflash-check.sh [ip[:port]]        default 192.168.0.100:5555
# Prints one PASS/FAIL/INFO line per item and writes the raw evidence to lineage/out/postflash-<date>.txt.
# Needs `adb root` to work (userdebug build).
cd "$(dirname "${BASH_SOURCE[0]}")/../.." || exit 1
DEV="${1:-192.168.0.100:5555}"
ADB="tools/platform-tools/adb.exe"
OUT="lineage/out/postflash-$(date +%Y%m%d-%H%M).txt"
A="$ADB -s $DEV"
sh() { MSYS_NO_PATHCONV=1 $A shell "$@" 2>/dev/null; }
res() { printf '%-5s %-28s %s\n' "$1" "$2" "$3" | tee -a "$OUT"; }
check() {  # check NAME "shell command" "regex that must match"
    local out; out=$(sh "$2" | tr -d '\r'); echo "## $1: $out" >> "$OUT"
    if echo "$out" | grep -qE "$3"; then res PASS "$1" "$(echo "$out" | head -1 | cut -c1-90)"; else res FAIL "$1" "$(echo "$out" | head -1 | cut -c1-90)"; fi
}

$ADB connect "$DEV" >/dev/null 2>&1
if ! sh 'echo ok' | grep -q ok; then echo "no adb at $DEV"; exit 1; fi
$A root >/dev/null 2>&1; sleep 3; $ADB connect "$DEV" >/dev/null 2>&1
echo "=== postflash check $(date) $DEV" | tee "$OUT"

check build            'getprop ro.build.version.release; getprop ro.lineage.version; getprop ro.product.model' '^15'
check kernel           'uname -r; uname -v' 'SMP PREEMPT'
check kernel-patches   'uname -v' '#[2-9]|#[1-9][0-9]'
check selinux          'getenforce' 'Enforcing|Permissive'
check dtb-galilei      'tr -d "\0" < /proc/device-tree/amlogic-dt-id' 'galilei'
check cpu-6-cores      'ls -d /sys/devices/system/cpu/cpu[0-9] | wc -l' '^6$'
check cpu-a73-2208     'cat /sys/devices/system/cpu/cpufreq/policy2/cpuinfo_max_freq' '^2208000'
check thermal-bound    'ls /sys/class/thermal/thermal_zone0 | grep -c cdev' '^1[0-9]'
check thermal-noerror  'dmesg | grep -c "binding zone soc_thermal"' '^0$'
check ram-3gb          'grep MemTotal /proc/meminfo' 'MemTotal: +3[0-9]{6}'
check gpu-mali         'dumpsys SurfaceFlinger | grep -m1 "^GLES: "' 'Mali-G52'
check vulkan           'pm list features | grep vulkan.version' 'vulkan.version'
check hwc-display      'dumpsys SurfaceFlinger --displays | grep -m1 activeMode' 'resolution=[0-9]+x[0-9]+'
check hdmi-hpd         'cat /sys/class/amhdmitx/amhdmitx0/hpd_state' '^1'
check hdmi-edid        'head -4 /sys/class/amhdmitx/amhdmitx0/edid | tr "\n" " "' 'Rx Manufacturer'
check audio-card       'cat /proc/asound/cards' 'AUGESOUND'
check audio-hal        'getprop init.svc.vendor.audio-hal' 'running'
check hdmi-audio-on    'cat /sys/class/amhdmitx/amhdmitx0/config | grep -m1 "audio on"' 'on'
check codecs-hw        'grep -c "OMX.amlogic.*decoder" /vendor/etc/media_codecs.xml' '^[5-9]|^[1-9][0-9]'
check vdec-modules     'lsmod | grep -c amvdec' '^[5-9]|^1[0-9]'
check video-fw-local    'cat /sys/module/tee/parameters/disable_flag' '^1'
check video-fw-no-tee-fail 'dmesg | grep -c "TEE fw loading failed"' '^0$'
check wifi-connected   'cmd wifi status | grep -m1 "Wifi is connected"' 'connected'
check wifi-ping        'ping -c 3 -W 2 8.8.8.8 | tail -1' 'rtt'
check wifi-idletime    'dmesg | grep -m1 dhd_idletime' 'dhd_idletime = 0'
check sdio-quiet       'dmesg | grep -c resp_timeout' '^[0-9]$|^[1-4][0-9]$'
check bt-on            'dumpsys bluetooth_manager | grep -m1 "state:"' 'ON'
check ir-remote-dev    'grep -m1 -A4 aml_keypad /proc/bus/input/devices | grep -c Name' '^1'
check ir-table-0x7f80  'grep -m1 "^custom_code" /vendor/etc/remote.tab1' '0x7f80'
check usb-host         'ls /sys/bus/usb/devices/ | grep -c usb' '^[1-9]'
check rtc              'ls /dev/rtc0' 'rtc0'
check emmc-sd          'ls /sys/block | grep -c mmcblk' '^[1-9]'
check storage-free     'df -h /data | tail -1' 'G'
check powerhal-looper  'logcat -d -s libperfmgr:* | grep -c "NodeLooperThread is not running"' '^0$'
check powerhal-init    'getprop vendor.powerhal.init' '^1'
check powerhint-planb   'grep -c "INTERACTIVE\"" /vendor/etc/powerhint.json' '^0$'
check init-galilei-rc   'ls /vendor/etc/init/init.galilei.rc' 'init.galilei.rc'
check gapps-overlay     'ls /product/overlay/ | grep -c ATVOverlay' '^1'
check no-deepsleep-lock 'cat /sys/power/wake_lock' 'galilei_nosuspend'
check cec-hal          'getprop init.svc.vendor.cec-hal-1-0' 'running'
check keystore         'getprop init.svc.vendor.keymaster-4-1 init.svc.keystore2 2>/dev/null; getprop | grep -c keymaster' '[1-9]'
check widevine-hal     'getprop init.svc.vendor.drm-widevine-hal-1-4' 'running'
check env-hook          'dd if=/dev/block/by-name/env bs=64k count=1 2>/dev/null | grep -a -c "store read bl33"' '^[1-9]'
check privapp-allowlist 'ls /product/etc/permissions | grep -c galilei' '^1'
check no-system-crash   'logcat -d -b crash 2>/dev/null | grep -c "FATAL EXCEPTION IN SYSTEM PROCESS"' '^0$'
check no-gms-crash      'logcat -d -b crash 2>/dev/null | grep -c "com.google.android.gms"' '^0$'
check gms-persistent    'pidof com.google.android.gms.persistent | wc -w' '^1'
check gservices-by-gsf  'dumpsys package providers 2>/dev/null | grep -A1 "gsf.gservices\]" | grep -c "com.google.android.gsf/"' '^1'
check gapps-gms        'pm list packages | grep -c "com.google.android.gms$"' '^1'
check gapps-playstore  'pm list packages | grep -c "com.android.vending$"' '^1'
check gapps-tvlauncher 'pm list packages | grep -c "com.google.android.tvlauncher$"' '^1'
check gapps-setupwizard 'pm list packages | grep -c "com.google.android.tungsten.setupwraith$"' '^1'
check launcher-home    'cmd package resolve-activity -a android.intent.action.MAIN -c android.intent.category.HOME | grep -m1 packageName' 'tvlauncher|lineageos'
check no-los-launcher  'pm list packages | grep -c "org.lineageos.tv.launcher$"' '^0$'
check uptime           'cut -d" " -f1 /proc/uptime' '^[0-9]'

# --- active tests
echo "--- standby cycle (screen off/on through the power HAL)" | tee -a "$OUT"
up0=$(sh 'cut -d" " -f1 /proc/uptime' | tr -dc 0-9.)
sh 'input keyevent 223' ; sleep 12
st=$(sh 'echo "trigger=$(cat /sys/power/early_suspend_trigger) hpd=$(cat /sys/class/amhdmitx/amhdmitx0/hpd_state) mode=$(cat /sys/class/display/mode) $(dumpsys power | grep -oE "mWakefulness=[A-Za-z]+")"' | tr -d '\r')
echo "## asleep: $st" >> "$OUT"
sh 'input keyevent 224' ; sleep 12
$ADB connect "$DEV" >/dev/null 2>&1
up1=$(sh 'cut -d" " -f1 /proc/uptime' | tr -dc 0-9.)
if [ -z "$up1" ]; then res FAIL standby "box unreachable after wake (hang)"; elif [ "${up1%.*}" -lt "${up0%.*}" ]; then res FAIL standby "box rebooted during the cycle (uptime $up0 -> $up1)"; else res PASS standby "asleep: $st | awake: $(sh 'dumpsys power | grep -oE "mWakefulness=[A-Za-z]+"; cat /sys/class/display/mode' | tr '\n' ' ')"; fi

echo "--- 30 s six-core stress" | tee -a "$OUT"
sh 'for i in 1 2 3 4 5 6; do nohup setsid sh -c "while :; do :; done" >/dev/null 2>&1 & done; sleep 30; t=$(cat /sys/class/thermal/thermal_zone0/temp); f0=$(cat /sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq); f2=$(cat /sys/devices/system/cpu/cpufreq/policy2/scaling_cur_freq); for p in $(ps -A -o PID,ARGS | grep -E "^ *[0-9]+ sh -c while" | awk "{print \$1}"); do kill $p; done; echo "temp=$t a53=$f0 a73=$f2"' | tr -d '\r' | tee -a "$OUT" | sed 's/^/stress: /'
echo "=== done; evidence in $OUT" | tee -a "$OUT"
