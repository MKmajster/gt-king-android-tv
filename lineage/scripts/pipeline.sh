#!/usr/bin/env bash
# Unattended pipeline for the galilei port (runs inside WSL, detached):
#   wait for repo sync -> install port into the tree -> build u-boot in-tree
#   -> vendor makefiles -> full LineageOS build (bacon + aml_upgrade).
# Launch:  nohup setsid bash /mnt/c/<path-to-repo>/lineage/scripts/pipeline.sh > /dev/null 2>&1 &
# Log:     ~/android/pipeline.log (plus ~/android/build-galilei.log for the Android build)
set -o pipefail
export PATH="$HOME/bin:$PATH"
TOP="${TOP:-$HOME/android/lineage}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"          # <repo>/lineage
LOG="$HOME/android/pipeline.log"

step() { echo "=== $(date '+%F %T') $*"; }

{
step "pipeline start (SRC=$SRC TOP=$TOP)"

step "waiting for repo sync"
while ! grep -q 'sync exit=' "$HOME/android/sync.log"; do sleep 60; done
rc=$(grep 'sync exit=' "$HOME/android/sync.log" | tail -1 | sed 's/.*sync exit=//')
step "repo sync finished with exit=$rc"
if [[ "$rc" != "0" ]]; then
    step "retrying repo sync once"
    (cd "$TOP" && repo sync -c -j4 --no-clone-bundle --no-tags --force-sync --optimized-fetch --retry-fetches=3 < /dev/null)
    step "retry exit=$?"
fi

step "setup-tree"
TOP="$TOP" bash "$SRC/scripts/setup-tree.sh" || { step "setup-tree FAILED"; exit 1; }

step "u-boot in-tree build (g12b_galilei_v1 + fip-radxa-zero2)"
if [[ -f "$TOP/vendor/beelink/galilei/radio/bootloader-radxafip.img" && -f "$TOP/hardware/amlogic/u-boot/build/u-boot.bin" ]]; then
    step "u-boot already built (radio/bootloader-radxafip.img + build/u-boot.bin exist) - skipping (git objects were purged to save disk, LOS build.sh needs git log)"
else
    bash "$TOP/device/beelink/galilei/build_u-boot.sh" || { step "u-boot build FAILED"; exit 1; }
fi
ls -la "$TOP/vendor/beelink/galilei/radio/"
# the in-tree build gives the pure LOS image (Radxa BL2); keep it, but ship the hybrid
# (stock Beelink BL2 = known-good LPDDR4 init + LOS FIP) as the package's bootloader.img
R="$TOP/vendor/beelink/galilei/radio"
[[ -f "$R/bootloader-radxafip.img" ]] || cp "$R/bootloader.img" "$R/bootloader-radxafip.img"
if python3 "$SRC/scripts/hybrid-bootloader.py" \
    /mnt/c/<path-to-repo>/backup/20260914-stock/bootloader.img \
    "$R/bootloader-radxafip.img" \
    "$R/bootloader-hybrid-stockbl2.img"; then
    cp "$R/bootloader-hybrid-stockbl2.img" "$R/bootloader.img"
    step "radio/bootloader.img = hybrid (stock BL2 + LOS FIP)"
else
    step "hybrid generation FAILED - radio/bootloader.img stays the pure LOS build"
fi
mkdir -p "$SRC/out/tree"
cp "$R"/bootloader*.img "$SRC/out/tree/" 2>/dev/null || true

step "vendor makefiles"
(cd "$TOP/device/beelink/galilei" && ./setup-makefiles.py) || { step "setup-makefiles FAILED"; exit 1; }
ls "$TOP/vendor/beelink/galilei"

step "android build"
TOP="$TOP" bash "$SRC/scripts/build.sh" bacon aml_upgrade
rc=$?
step "android build exit=$rc"
if [[ "$rc" == "0" ]]; then
    mkdir -p "$SRC/out/tree"
    cp "$TOP"/out/target/product/galilei/lineage-*.zip "$TOP"/out/target/product/galilei/aml_upgrade_package.img "$SRC/out/tree/" 2>/dev/null
    ls -la "$SRC/out/tree/"
fi
step "pipeline end"
} >> "$LOG" 2>&1
