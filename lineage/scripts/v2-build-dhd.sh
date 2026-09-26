#!/usr/bin/env bash
# v2: AP6275S (BCM43752A2) Wi-Fi driver bcmdhd.101.10.591.x (same source as v1) built against the
# v2 kernel (voodik's source/config, ~/v2/kout) with Linaro GCC 6.3 -> ~/v2/out/modules/dhd.ko.
#   bash lineage/scripts/v2-build-dhd.sh      (WSL)
set -euo pipefail
K=$HOME/v2/kernel-voodik
O=$HOME/v2/kout
TC=$HOME/v2/tc/gcc6/bin/aarch64-linux-gnu-
SRC=$HOME/android/lineage/kernel/amlogic/kernel-modules/dhd-driver/bcmdhd.101.10.591.x
W=$HOME/v2/dhd
OUT=$HOME/v2/out/modules
rm -rf "$W"; cp -a "$SRC" "$W"; mkdir -p "$OUT"
# voodik's 4.9 kernel carries the 4.12 cfg80211 API (wiphy->max_sched_scan_reqs, no
# WIPHY_FLAG_SUPPORTS_SCHED_SCAN) while LINUX_VERSION_CODE still says 4.9: take the new-API branch.
python3 - "$W" <<'EOF'
import sys, pathlib
w = pathlib.Path(sys.argv[1])
for f, ctx in (("dhd_config.c", "conf->max_sched_scan_reqs > 0)\n\t\twdev->wiphy->flags"),
               ("wl_cfg80211.c", "\twdev->wiphy->flags |= WIPHY_FLAG_SUPPORTS_SCHED_SCAN;")):
    p = w / f; s = p.read_text(errors="surrogateescape")
    guard = "#if (LINUX_VERSION_CODE < KERNEL_VERSION(4, 12, 0))\n"
    i = s.index(ctx); j = s.rindex(guard, 0, i)
    s = s[:j] + "#if 0 /* v2: backported 4.12 cfg80211 sched-scan API */\n" + s[j + len(guard):]
    p.write_text(s, errors="surrogateescape"); print("patched", f)
EOF
# the rest of the 4.10..4.17 cfg80211 guards (core-kernel ones stay on LINUX_VERSION_CODE)
python3 "$(dirname "${BASH_SOURCE[0]}")/v2-dhd-cfg80211-compat.py" "$W"
REL=$(python3 -c 'import os,sys; print(os.path.relpath(sys.argv[1], sys.argv[2]))' "$W" "$K")
cd "$K"
nice -n 19 make O="$O" ARCH=arm64 CROSS_COMPILE="$TC" M="$REL" KERNEL_SRC="$K" \
    CONFIG_BCMDHD=m CONFIG_BCMDHD_SDIO=y CONFIG_DHD_USE_STATIC_BUF=y \
    KCFLAGS="-DWL_CFG80211_VERSION_CODE=0x041100" -k -j6 modules > "$HOME/v2/dhd-build.log" 2>&1 \
    || { grep -n -E "error:|Error [0-9]" "$HOME/v2/dhd-build.log" | head -30; exit 1; }
KO=$(find "$W" -name "dhd.ko" | head -1)
"${TC}strip" --strip-debug -o "$OUT/dhd.ko" "$KO"
ls -l "$OUT/dhd.ko"
/sbin/modinfo "$OUT/dhd.ko" | grep -E "vermagic|depends|version:" || true
# every imported symbol must be exported by the v2 kernel
python3 - "$OUT/dhd.ko" "$O/Module.symvers" <<'EOF'
import subprocess, sys
ours = {}
for l in open(sys.argv[2]):
    p = l.split()
    if len(p) >= 2: ours[p[1]] = int(p[0], 16)
bad = []
for l in subprocess.run(["/sbin/modprobe", "--dump-modversions", sys.argv[1]], capture_output=True, text=True).stdout.splitlines():
    crc, sym = l.split()[:2]
    if sym not in ours or ours[sym] != int(crc, 16): bad.append(sym)
print("dhd.ko imports resolved by the v2 kernel:", "all" if not bad else "MISSING " + " ".join(bad))
EOF
