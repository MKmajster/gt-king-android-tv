#!/usr/bin/env bash
# "Everything original" USB Burning Tool package: the stock-restore+stockbl package (stock bootloader,
# stock multi-DTB partition table, boot/recovery/dtbo/logo/misc/vbmeta/odm/product/vendor/system from the
# sha1-verified backup) PLUS the box's own env, tee, param and cri_data images from the same backup.
# RPMB cannot be flashed (and was never touched); reserved is written through _aml_dtb only.
#   TOP=~/android/lineage lineage/scripts/make-stock-full-package.sh
# Output: lineage/out/tree/aml_upgrade_package_stock-restore-full+stockbl.img
set -euo pipefail
TOP="${TOP:-$HOME/android/lineage}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$(cd "$SRC/.." && pwd)"
PACKER="$TOP/out/host/linux-x86/bin/aml_image_packer"
D="$TOP/device/beelink/galilei/factory"
BK="$REPO/backup/20260914-stock"
STOCKBL="$SRC/out/u-boot-stock-beelink.bin"
[[ -x "$PACKER" && -f "$STOCKBL" ]] || { echo "missing packer or $STOCKBL" >&2; exit 1; }
( cd "$BK" && sha1sum -c --quiet SHA1SUMS ) || { echo "stock backup sha1 mismatch" >&2; exit 1; }
S="$SRC/out/stage-stock-full"; rm -rf "$S"; mkdir -p "$S"
cp "$STOCKBL" "$S/u-boot.bin"
cp "$REPO/research/device/boot-second.bin" "$S/dtb.img"
sed 's/erase_bootloader *= *1/erase_bootloader    = 0/' "$D/aml_sdc_burn.ini" > "$S/aml_sdc_burn.ini"
cp "$D/platform.conf" "$S/"
for f in boot recovery dtbo logo system vendor product odm vbmeta misc env tee param cri_data; do cp "$BK/$f.img" "$S/"; done
cat > "$S/image.cfg" <<'EOF'
[LIST_NORMAL]
file="u-boot.bin"		main_type="USB"		sub_type="DDR"
file="u-boot.bin"		main_type="USB"		sub_type="UBOOT"
file="u-boot.bin"		main_type="UBOOT"		sub_type="aml_sdc_burn"
file="aml_sdc_burn.ini"		main_type="ini"		sub_type="aml_sdc_burn"
file="dtb.img"		main_type="dtb"		sub_type="meson1"
file="platform.conf"		main_type="conf"		sub_type="platform"
file="dtb.img"		main_type="PARTITION"		sub_type="_aml_dtb"
file="u-boot.bin"		main_type="PARTITION"		sub_type="bootloader"
file="env.img"		main_type="PARTITION"		sub_type="env"
file="tee.img"		main_type="PARTITION"		sub_type="tee"
file="param.img"		main_type="PARTITION"		sub_type="param"
file="cri_data.img"		main_type="PARTITION"		sub_type="cri_data"
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
OUT="$SRC/out/tree/aml_upgrade_package_stock-restore-full+stockbl.img"
mkdir -p "$SRC/out/tree"
"$PACKER" -r "$S/image.cfg" "$S/" "$OUT"
rm -rf "$S"
ls -la "$OUT"
cp "$OUT" /mnt/c/<path-to-repo>-flash/
echo DONE
