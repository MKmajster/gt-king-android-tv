#!/usr/bin/env bash
# Build the "chainload" USB Burning Tool package for galilei: same as aml_upgrade_package.img but
# WITHOUT touching the bootloader partition and WITH the raw galilei BL33 in the new 'bl33' partition.
# The stock Beelink bootloader stays; its env 'preboot' hook (chainload-env.py --set) jumps into bl33.
#   TOP=~/android/lineage lineage/scripts/make-chainload-package.sh
# Output: $TOP/out/target/product/galilei/aml_upgrade_package_chainload.img (+ copy in lineage/out/tree/)
set -euo pipefail
TOP="${TOP:-$HOME/android/lineage}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
P="$TOP/out/target/product/galilei"
D="$TOP/device/beelink/galilei/factory"
PACKER="$TOP/out/host/linux-x86/bin/aml_image_packer"
BL33="$TOP/hardware/amlogic/u-boot/build/u-boot.bin"
[[ -x "$PACKER" ]] || { echo "missing $PACKER (build aml_image_packer first: m aml_image_packer)" >&2; exit 1; }
[[ -f "$BL33" ]] || { echo "missing $BL33 (device/beelink/galilei/build_u-boot.sh)" >&2; exit 1; }
for f in boot.img recovery.img dtbo.img vbmeta.img super.img logo.img dtb.img; do
    [[ -f "$P/$f" ]] || { echo "missing $P/$f" >&2; exit 1; }
done
STAGE="$P/aml_chainload"; rm -rf "$STAGE"; mkdir -p "$STAGE"
# u-boot.bin in the package is only used by USB Burning Tool for the BootROM stage (DDR/UBOOT) and
# aml_sdc_burn; it is NOT flashed (no PARTITION bootloader line). Use the stock Beelink bootloader
# here so that even that stage runs known-good code on this board.
cp /mnt/c/<path-to-repo>/lineage/out/u-boot-stock-beelink.bin "$STAGE/u-boot.bin"
cp "$D/aml_sdc_burn.ini" "$D/platform.conf" "$STAGE/"
sed 's/erase_bootloader *= *1/erase_bootloader    = 0/' "$D/aml_sdc_burn.ini" > "$STAGE/aml_sdc_burn.ini"
cp "$D/image_upgrade_chainload.cfg" "$STAGE/image.cfg"
for f in boot.img recovery.img dtbo.img vbmeta.img super.img logo.img dtb.img; do cp "$P/$f" "$STAGE/"; done
# bl33.img: raw BL33 padded to 4 KiB (partition is 2 MiB); chainload reads 0x140000 bytes
python3 - "$BL33" "$STAGE/bl33.img" <<'PY'
import sys
d = open(sys.argv[1], "rb").read()
assert len(d) <= 0x140000, "BL33 larger than the 0x140000 read in the preboot hook"
d += b"\0" * (-len(d) % 4096)
open(sys.argv[2], "wb").write(d)
print("bl33.img", len(d), "bytes")
PY
OUT="$P/aml_upgrade_package_chainload.img"
"$PACKER" -r "$STAGE/image.cfg" "$STAGE/" "$OUT"
ls -la "$OUT"
mkdir -p "$SRC/out/tree" && cp "$OUT" "$SRC/out/tree/"
echo "chainload package: $OUT"
