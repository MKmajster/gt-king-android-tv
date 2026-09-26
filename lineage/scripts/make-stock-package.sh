#!/usr/bin/env bash
# Build a USB Burning Tool package that puts the STOCK Beelink partition layout and images back
# (the way back from LineageOS). Uses the sha1-verified dumps in backup/20260914-stock/.
# NOT included on purpose: bootloader, env, tee, rpmb, cri_data, param (never flashed; the stock
# bootloader is still in place in variant B anyway). data/cache are recreated empty by the burn.
#   TOP=~/android/lineage lineage/scripts/make-stock-package.sh
# Output: lineage/out/tree/aml_upgrade_package_stock-restore.img
set -euo pipefail
TOP="${TOP:-$HOME/android/lineage}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$(cd "$SRC/.." && pwd)"
BK="$REPO/backup/20260914-stock"
D="$TOP/device/beelink/galilei/factory"
PACKER="$TOP/out/host/linux-x86/bin/aml_image_packer"
[[ -x "$PACKER" ]] || { echo "missing $PACKER (m aml_image_packer)" >&2; exit 1; }
for f in boot recovery dtbo logo system vendor product odm vbmeta misc; do
    [[ -f "$BK/$f.img" ]] || { echo "missing $BK/$f.img" >&2; exit 1; }
done
( cd "$BK" && sha1sum -c --quiet SHA1SUMS ) || { echo "stock backup sha1 mismatch - refusing" >&2; exit 1; }

STAGE="$SRC/out/stage-stock"; rm -rf "$STAGE"; mkdir -p "$STAGE"
cp "$SRC/out/u-boot-stock-beelink.bin" "$STAGE/u-boot.bin"          # BootROM/DDR stage only, not flashed
# stock multi-DTB (g12b_w400_a + g12b_w400_b) from the stock boot.img "second" area = the stock partition table
cp "$REPO/research/device/boot-second.bin" "$STAGE/dtb.img"
cp "$D/platform.conf" "$STAGE/"
sed 's/erase_bootloader *= *1/erase_bootloader    = 0/' "$D/aml_sdc_burn.ini" > "$STAGE/aml_sdc_burn.ini"
for f in boot recovery dtbo logo system vendor product odm vbmeta misc; do cp "$BK/$f.img" "$STAGE/"; done
cat > "$STAGE/image.cfg" <<'EOF'
[LIST_NORMAL]
file="u-boot.bin"		main_type="USB"		sub_type="DDR"
file="u-boot.bin"		main_type="USB"		sub_type="UBOOT"
file="u-boot.bin"		main_type="UBOOT"		sub_type="aml_sdc_burn"
file="aml_sdc_burn.ini"		main_type="ini"		sub_type="aml_sdc_burn"
file="dtb.img"		main_type="dtb"		sub_type="meson1"
file="platform.conf"		main_type="conf"		sub_type="platform"
file="dtb.img"		main_type="PARTITION"		sub_type="_aml_dtb"
file="boot.img"		main_type="PARTITION"		sub_type="boot"
file="recovery.img"		main_type="PARTITION"		sub_type="recovery"
file="dtbo.img"		main_type="PARTITION"		sub_type="dtbo"
file="logo.img"		main_type="PARTITION"		sub_type="logo"
file="misc.img"		main_type="PARTITION"		sub_type="misc"
file="vbmeta.img"		main_type="PARTITION"		sub_type="vbmeta"
file="odm.img"		main_type="PARTITION"		sub_type="odm"
file="product.img"		main_type="PARTITION"		sub_type="product"
file="vendor.img"		main_type="PARTITION"		sub_type="vendor"
file="system.img"		main_type="PARTITION"		sub_type="system"
EOF
mkdir -p "$SRC/out/tree"
OUT="$SRC/out/tree/aml_upgrade_package_stock-restore.img"
"$PACKER" -r "$STAGE/image.cfg" "$STAGE/" "$OUT"
ls -la "$OUT"
rm -rf "$STAGE"
echo "stock-restore package: $OUT"
