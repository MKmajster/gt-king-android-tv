#!/system/bin/sh
# Log ARMSX2 performance while someone plays: every PerfLog line (fps, EE/GS/VU thread load) with
# CPU/GPU clocks and temperatures appended, into /data/local/tmp/ps2-perflog.txt, for $1 seconds.
#   adb shell "nohup sh /data/local/tmp/ps2-perflog.sh 360 >/dev/null 2>&1 &"
SECS=${1:-360}
OUT=/data/local/tmp/ps2-perflog.txt
: > $OUT
logcat -c
T0=$(date +%s)
logcat -v time -s STDOUT:W | while read -r line; do
    case "$line" in
    *PerfLog:*)
        t=""; for z in /sys/class/thermal/thermal_zone*/temp; do t="$t$(( $(cat $z) / 1000 ))C "; done
        echo "$(date +%T) ${line#*PerfLog: } | a53=$(( $(cat /sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq) / 1000 )) a73=$(( $(cat /sys/devices/system/cpu/cpufreq/policy2/scaling_cur_freq) / 1000 )) gpu=$(( $(cat /sys/class/devfreq/ffe40000.bifrost/cur_freq) / 1000000 )) $t" >> $OUT ;;
    *ANDROID_LAUNCH_GAME*|*"ELF "*|*"is executing"*) echo "$(date +%T) ${line#*STDOUT  : }" >> $OUT ;;
    esac
    [ $(( $(date +%s) - T0 )) -ge "$SECS" ] && break
done
echo "$(date +%T) end" >> $OUT
