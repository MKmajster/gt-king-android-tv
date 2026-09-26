#!/usr/bin/env bash
# Build u-boot for Beelink GT-King Pro (galilei) - lives in
# hardware/amlogic/u-boot_build/ next to build_radxa02pro.sh.
#
# BL2/BL30/BL31 and the DDR firmware come from fip-radxa-zero2 (Radxa Zero 2
# Pro: A311D + 4 GB LPDDR4, same G12B fip format as this box). BL2 carries
# Radxa's LPDDR4 timing; if the box does not come up with it, use
# hybrid-bootloader.sh to combine the stock Beelink BL2 with this fip.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# reproducible timestamp from the u-boot commit; fall back to "now" when the git objects are gone
export SOURCE_DATE_EPOCH=$(git -C "../u-boot" log -1 --pretty=%ct HEAD 2>/dev/null || date +%s)

BOARD=g12b_galilei_v1
FIP_DIR=fip-radxa-zero2
UBOOT_BIN="${SCRIPT_DIR}/uboot-bins/u-boot.bin"

LINEAGE_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DEVICE_PATH="${LINEAGE_ROOT}/device/beelink/galilei"
VENDOR_PATH="${LINEAGE_ROOT}/vendor/beelink/galilei"

[[ -d "${VENDOR_PATH}" ]] && mkdir -p "${VENDOR_PATH}/radio"

./build.sh "$BOARD"
./generate-bins-new.sh "$FIP_DIR" ../u-boot/build/u-boot.bin "${BOARD}-base"
[[ -d "${VENDOR_PATH}" ]] && cp "$UBOOT_BIN" "${VENDOR_PATH}/radio/bootloader.img"

echo "u-boot images in $(readlink -f uboot-bins):"
ls -la uboot-bins/

if [[ -d "${DEVICE_PATH}" && -x "${DEVICE_PATH}/setup-makefiles.py" ]]; then
    cd "$DEVICE_PATH" && ./setup-makefiles.py
fi
