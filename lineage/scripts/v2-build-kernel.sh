#!/usr/bin/env bash
# v2 (64-bit userspace) kernel: voodik's ODROID-N2 LineageOS 22.1 kernel (github voodik/
# android_kernel_voodik_odroidg12, commit 660a3bebdf92 = the kernel inside his 20260528 ATV build),
# his config (IKCONFIG from that boot.img, ~/voodik/voodik.config) and his compiler (Linaro GCC 6.3.1
# 2017.05). Goal: symbol CRCs identical to his prebuilt modules (mali.ko r51p0 etc.) so they load.
#   bash lineage/scripts/v2-build-kernel.sh [config] [jobs]     (runs in WSL; log ~/v2/kbuild.log)
set -euo pipefail
K=$HOME/v2/kernel-voodik
O=$HOME/v2/kout
TC=$HOME/v2/tc/gcc6/bin/aarch64-linux-gnu-
# neutral build identity in /proc/version ("Linux version ... (MKmajster@build)") instead of the
# local user and host name
export KBUILD_BUILD_USER=MKmajster KBUILD_BUILD_HOST=build
CFG=${1:-$HOME/voodik/voodik.config}
J=${2:-6}
LOG=$HOME/v2/kbuild.log
mkdir -p "$O"
cd "$K"
# His IKCONFIG lists only the enabled options (no "# CONFIG_X is not set" lines). Plain olddefconfig
# would switch ~2600 absent options to their Kconfig defaults (e.g. FHANDLE=y, which does not even
# compile in this tree). So: expand once to learn every symbol, then mark all absent ones "not set".
cp "$CFG" "$O/.config"
make O="$O" ARCH=arm64 CROSS_COMPILE="$TC" olddefconfig > "$LOG" 2>&1
python3 - "$CFG" "$O/.config" <<'EOF2'
import re, sys
his, full = sys.argv[1:3]
want = {}
for l in open(his):
    m = re.match(r"(CONFIG_\w+)=(.*)", l)
    if m: want[m.group(1)] = m.group(2)
out = []
for l in open(full):
    m = re.match(r"(CONFIG_\w+)=(.*)", l) or re.match(r"# (CONFIG_\w+) is not set", l)
    if not m:
        continue
    k = m.group(1)
    out.append(f"{k}={want[k]}" if k in want else f"# {k} is not set")
open(full, "w").write(chr(10).join(out) + chr(10))
EOF2
set +e
{
    echo "=== $(date '+%F %T') v2 kernel build, config $CFG, -j$J"
    make O="$O" ARCH=arm64 CROSS_COMPILE="$TC" olddefconfig
    nice -n 19 make O="$O" ARCH=arm64 CROSS_COMPILE="$TC" -j"$J" Image.gz modules
} >> "$LOG" 2>&1
rc=$?
set -e
echo "=== $(date '+%F %T') done rc=$rc" >> "$LOG"
[ $rc = 0 ] || { grep -n -E "error:|Error [0-9]" "$LOG" | tail -15; exit 1; }
tail -3 "$LOG"
ls -l "$O/arch/arm64/boot/Image.gz" "$O/Module.symvers"
