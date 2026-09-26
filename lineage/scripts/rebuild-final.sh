#!/usr/bin/env bash
# 2026-09-24 evening: rebuild after the first successful LOS boot:
#   device tree: remote.tab1 = stock nec-cursor-31 (0x7f80); DTS: vddcpu tables, ethmac single
#   compatible + stmmaceth clock (kernel DTB) -> incremental Android build (vendor + boot dtb) ->
#   multi-DTB (galilei + stock w400_b with the LOS partition table) -> Burning Tool package
#   aml_upgrade_package_chainload+stockbl+multidtb-final.img (BL33 v4 from the u-boot build dir).
# Run inside WSL:  nohup setsid bash /mnt/c/<path-to-repo>/lineage/scripts/rebuild-final.sh > /dev/null 2>&1 &
# Log: ~/android/rebuild-final.log
set -o pipefail
export PATH="$HOME/bin:$PATH"
TOP="${TOP:-$HOME/android/lineage}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="$HOME/android/rebuild-final.log"
step() { echo "=== $(date '+%F %T') $*"; }
{
step "rebuild-final start"
TOP="$TOP" bash "$SRC/scripts/setup-tree.sh" || { step "setup-tree FAILED"; exit 1; }
grep -q "custom_code = 0x7f80" "$TOP/device/beelink/galilei/remote/remote.tab1" || { step "remote.tab1 not the 0x7f80 table"; exit 1; }
grep -q '"stmmaceth"' "$TOP/kernel/amlogic/linux-4.9/arch/arm64/boot/dts/amlogic/g12b_s922x_galilei.dts" || { step "DTS in tree lacks the ethmac fix"; exit 1; }
grep -q "CONFIG_GALILEI_FIXED_BOOTENV" "$TOP/hardware/amlogic/u-boot/common/main.c" || { step "u-boot tree lacks v4"; exit 1; }
python3 - "$TOP/hardware/amlogic/u-boot/build/u-boot.bin" <<'PY'
import sys, zlib
d = open(sys.argv[1], "rb").read(); d += b"\0" * (-len(d) % 4096)
c = "%08x" % zlib.crc32(d); print("u-boot build bl33 crc32", c); assert c == "ee34b493", "not BL33 v4"
PY
[[ $? == 0 ]] || { step "u-boot build dir is not v4"; exit 1; }
step "android build (incremental)"
TOP="$TOP" bash "$SRC/scripts/build.sh" bacon aml_upgrade
rc=$?; step "android build exit=$rc"
[[ "$rc" == "0" ]] || { step "build failed - last errors:"; grep -nE "FAILED:|error:" "$HOME/android/build-galilei.log" | grep -v -- "-Werror" | tail -20; exit 1; }
P="$TOP/out/target/product/galilei"
grep -q "custom_code = 0x7f80" "$P/vendor/etc/remote.tab1" || { step "vendor remote.tab1 not updated"; exit 1; }
step "multi-dtb from the fresh dtb.img"
python3 "$SRC/scripts/make-multi-dtb.py" "$SRC/out/multi-dtb-final+w400b-losparts.img" "$P/dtb.img" "$SRC/out/stock-w400_b+losparts.dtb" || { step "multi-dtb FAILED"; exit 1; }
step "package"
DTBIMG="$SRC/out/multi-dtb-final+w400b-losparts.img" OUT_SUFFIX="+multidtb-final" ONLY_CHAINLOAD=1 TOP="$TOP" \
    bash "$SRC/scripts/make-packages-with-bootloader.sh" 2>&1 | grep -E "dtb.img <-|bl33.img|Size=|Install image|DONE|rror" || { step "package FAILED"; exit 1; }
cp "$P"/lineage-*.zip "$SRC/out/tree/" 2>/dev/null
(cd "$SRC/out/tree" && sha256sum aml_upgrade_package_chainload+stockbl+multidtb-final.img > SHA256SUMS-final)
ls -la "$SRC/out/tree/"
step "rebuild-final end"
} >> "$LOG" 2>&1
