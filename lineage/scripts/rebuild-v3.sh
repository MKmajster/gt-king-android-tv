#!/usr/bin/env bash
# 2026-09-22 rebuild after the root-cause analysis (run inside WSL, detached):
#   1. refresh the port in the tree (device tree: AP6275S/BCM43752A2 firmware, adb tcp; u-boot board
#      generator: preboot = CONFIG_PREBOOT with forceupdate)
#   2. u-boot -> BL33 v3 (lineage/out/bl33-v3.img, 4 KiB padded)
#   3. incremental LineageOS build (vendor firmware + props changed -> new super.img / OTA zip)
#   4. USB Burning Tool packages, all with BL33 v3: chainload, chainload+stockbl, stock-restore+stockbl
# Launch:  nohup setsid bash /mnt/c/<path-to-repo>/lineage/scripts/rebuild-v3.sh > /dev/null 2>&1 &
# Log:     ~/android/rebuild-v3.log (Android build details in ~/android/build-galilei.log)
set -o pipefail
export PATH="$HOME/bin:$PATH"
TOP="${TOP:-$HOME/android/lineage}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"          # <repo>/lineage
LOG="$HOME/android/rebuild-v3.log"
step() { echo "=== $(date '+%F %T') $*"; }
{
step "rebuild-v3 start (SRC=$SRC TOP=$TOP)"

step "setup-tree (device tree + u-boot board regen)"
TOP="$TOP" bash "$SRC/scripts/setup-tree.sh" || { step "setup-tree FAILED"; exit 1; }
grep -n 'setenv("preboot", CONFIG_PREBOOT)' "$TOP/hardware/amlogic/u-boot/board/amlogic/g12b_galilei_v1/g12b_galilei_v1.c" \
    || { step "board .c lacks the v3 preboot replace"; exit 1; }
grep -n '"forceupdate;"' "$TOP/hardware/amlogic/u-boot/board/amlogic/configs/g12b_galilei_v1.h" \
    || { step "config .h lacks forceupdate in CONFIG_PREBOOT"; exit 1; }

step "u-boot build (BL33 v3)"
bash "$TOP/device/beelink/galilei/build_u-boot.sh" || { step "u-boot build FAILED"; exit 1; }
UB="$TOP/hardware/amlogic/u-boot/build/u-boot.bin"
ls -la "$UB"
python3 - "$UB" "$SRC/out/bl33-v3.img" <<'PY'
import sys
d = open(sys.argv[1], "rb").read()
assert len(d) <= 0x140000, "BL33 larger than the 0x140000 read in the preboot hook"
assert b"forceupdate" in d, "forceupdate command missing from the built u-boot"
assert b"run bcb_cmd; run factory_reset_poweroff_protect;run upgrade_check;run init_display;run storeargs;forceupdate;" in d, \
    "compiled CONFIG_PREBOOT does not contain forceupdate"
d += b"\0" * (-len(d) % 4096)
open(sys.argv[2], "wb").write(d)
print("bl33-v3.img", len(d), "bytes")
PY
[[ -f "$SRC/out/bl33-v3.img" ]] || { step "bl33-v3.img not written"; exit 1; }
# the hybrid bootloader (stock BL2 + LOS FIP) is what the device tree ships as radio/bootloader.img
R="$TOP/vendor/beelink/galilei/radio"
cp "$R/bootloader.img" "$R/bootloader-radxafip.img"
python3 "$SRC/scripts/hybrid-bootloader.py" /mnt/c/<path-to-repo>/backup/20260914-stock/bootloader.img \
    "$R/bootloader-radxafip.img" "$R/bootloader-hybrid-stockbl2.img" && cp "$R/bootloader-hybrid-stockbl2.img" "$R/bootloader.img"
(cd "$TOP/device/beelink/galilei" && ./setup-makefiles.py) || { step "setup-makefiles FAILED"; exit 1; }

step "android build (incremental)"
TOP="$TOP" bash "$SRC/scripts/build.sh" bacon aml_upgrade
rc=$?
step "android build exit=$rc"
[[ "$rc" == "0" ]] || { step "build failed - last errors:"; grep -nE "FAILED:|error:" "$HOME/android/build-galilei.log" | grep -v -- "-Werror" | tail -20; exit 1; }
P="$TOP/out/target/product/galilei"
for f in fw_bcm43752a2_ag.bin nvram_ap6275s.txt clm_bcm43752a2_ag.blob config_bcm43752a2_ag.txt; do
    [[ -f "$P/vendor/firmware/wifi/$f" ]] && echo "vendor/firmware/wifi/$f OK" || { step "missing vendor/firmware/wifi/$f"; exit 1; }
done
grep -n "service.adb.tcp.port" "$P/system/build.prop" || step "WARNING: service.adb.tcp.port not in system/build.prop"

step "packages (BL33 v3)"
rm -f "$SRC"/out/tree/aml_upgrade_package_chainload+stockbl+recovery.img
TOP="$TOP" bash "$SRC/scripts/make-chainload-package.sh" || { step "chainload package FAILED"; exit 1; }
TOP="$TOP" bash "$SRC/scripts/make-packages-with-bootloader.sh" || { step "+stockbl packages FAILED"; exit 1; }
cp "$P"/lineage-*.zip "$SRC/out/tree/" 2>/dev/null
(cd "$SRC/out/tree" && sha256sum *.img *.zip > SHA256SUMS)
ls -la "$SRC/out/tree/"
step "rebuild-v3 end"
} >> "$LOG" 2>&1
