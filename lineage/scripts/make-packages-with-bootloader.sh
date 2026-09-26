#!/usr/bin/env bash
# Re-pack the chainload and stock-restore USB Burning Tool packages WITH the stock Beelink bootloader
# as a flashed partition (PARTITION bootloader = stock u-boot.bin). Needed when the bootloader area on
# the eMMC was erased (box drops into BootROM USB mode on a clean power-on).
#   TOP=~/android/lineage lineage/scripts/make-packages-with-bootloader.sh
# Outputs: lineage/out/tree/aml_upgrade_package_chainload+stockbl.img
#          lineage/out/tree/aml_upgrade_package_stock-restore+stockbl.img
set -euo pipefail
TOP="${TOP:-$HOME/android/lineage}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$(cd "$SRC/.." && pwd)"
PACKER="$TOP/out/host/linux-x86/bin/aml_image_packer"
P="$TOP/out/target/product/galilei"
D="$TOP/device/beelink/galilei/factory"
BK="$REPO/backup/20260914-stock"
STOCKBL="$SRC/out/u-boot-stock-beelink.bin"
# PARTITION bootloader = the stock u-boot with the chainload hook in its compiled-in default env
# (patch-stock-bl33-env.py): the Burning Tool ends every burn with a saveenv of the DEFAULT env, so
# only a default preboot survives. The USB DDR/UBOOT items (the u-boot the tool itself runs during
# the burn) stay the plain stock u-boot. HOOKBL=none ships the plain stock u-boot as the partition.
HOOKBL="${HOOKBL:-$SRC/out/tree/hookbl/u-boot-stock+hook.bin}"
# Optional: DTBIMG=<file> replaces $P/dtb.img in the chainload package (e.g. the multi-DTB from
# make-multi-dtb.py), OUT_SUFFIX names the output, ONLY_CHAINLOAD=1 skips the stock-restore package.
DTBIMG="${DTBIMG:-$P/dtb.img}"
OUT_SUFFIX="${OUT_SUFFIX:-}"
[[ -x "$PACKER" && -f "$STOCKBL" ]] || { echo "missing packer or $STOCKBL" >&2; exit 1; }
python3 - "$STOCKBL" <<'PY'
import sys; d = open(sys.argv[1], "rb").read()
assert d[0x10:0x14] == b"@AML", "stock u-boot.bin: no @AML BL2 header at 0x10"
print("stock u-boot.bin OK:", len(d), "bytes")
PY
mkdir -p "$SRC/out/tree"

pack() {  # $1 stage dir, $2 output
    "$PACKER" -r "$1/image.cfg" "$1/" "$2"
    ls -la "$2"
}

# --- 1. chainload + stock bootloader ---------------------------------------------------------
S="$SRC/out/stage-chainload-bl"; rm -rf "$S"; mkdir -p "$S"
cp "$STOCKBL" "$S/u-boot.bin"
[[ "$HOOKBL" != none && -f "$HOOKBL" ]] && { cp "$HOOKBL" "$S/u-boot-hook.bin"; echo "PARTITION bootloader <- $HOOKBL (hook in default env)"; }
sed 's/erase_bootloader *= *1/erase_bootloader    = 0/' "$D/aml_sdc_burn.ini" > "$S/aml_sdc_burn.ini"
cp "$D/platform.conf" "$S/"
for f in boot.img recovery.img dtbo.img vbmeta.img super.img logo.img; do cp "$P/$f" "$S/"; done
cp "$DTBIMG" "$S/dtb.img"; echo "dtb.img <- $DTBIMG"
python3 - "$TOP/hardware/amlogic/u-boot/build/u-boot.bin" "$S/bl33.img" <<'PY'
import sys; d = open(sys.argv[1], "rb").read(); assert len(d) <= 0x140000
d += b"\0" * (-len(d) % 4096); open(sys.argv[2], "wb").write(d); print("bl33.img", len(d))
PY
# env partition with the chainload hook (lineage/scripts/make-env-image.py from the env dumped off
# the working box): shipping it means the stock u-boot runs the hook right after the Burning Tool
# flash, without anyone installing it over a serial console (to be verified: the tool's own u-boot
# must not rewrite env after the partition write).
ENVIMG="${ENVIMG:-}"   # env.img never survives the tool's final saveenv (see HOOKBL) - only if given explicitly
[[ -f "$ENVIMG" ]] && { cp "$ENVIMG" "$S/env.img"; echo "env.img <- $ENVIMG"; }
{ grep -v 'sub_type="bl33"' "$D/image_upgrade_chainload.cfg"
  if [[ -f "$S/u-boot-hook.bin" ]]; then echo 'file="u-boot-hook.bin"		main_type="PARTITION"		sub_type="bootloader"'; else echo 'file="u-boot.bin"		main_type="PARTITION"		sub_type="bootloader"'; fi
  echo 'file="bl33.img"		main_type="PARTITION"		sub_type="bl33"'
  [[ -f "$S/env.img" ]] && echo 'file="env.img"		main_type="PARTITION"		sub_type="env"'; } > "$S/image.cfg"
cat "$S/image.cfg"
pack "$S" "$SRC/out/tree/aml_upgrade_package_chainload+stockbl${OUT_SUFFIX}.img"
rm -rf "$S"
[[ "${ONLY_CHAINLOAD:-0}" == 1 ]] && { echo DONE; exit 0; }

# --- 2. stock restore + stock bootloader -----------------------------------------------------
( cd "$BK" && sha1sum -c --quiet SHA1SUMS ) || { echo "stock backup sha1 mismatch" >&2; exit 1; }
S="$SRC/out/stage-stock-bl"; rm -rf "$S"; mkdir -p "$S"
cp "$STOCKBL" "$S/u-boot.bin"
cp "$REPO/research/device/boot-second.bin" "$S/dtb.img"
sed 's/erase_bootloader *= *1/erase_bootloader    = 0/' "$D/aml_sdc_burn.ini" > "$S/aml_sdc_burn.ini"
cp "$D/platform.conf" "$S/"
for f in boot recovery dtbo logo system vendor product odm vbmeta misc; do cp "$BK/$f.img" "$S/"; done
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
pack "$S" "$SRC/out/tree/aml_upgrade_package_stock-restore+stockbl.img"
rm -rf "$S"
echo DONE
