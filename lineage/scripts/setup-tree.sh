#!/usr/bin/env bash
# Install the galilei port into a synced LineageOS 22.2 tree (run inside WSL).
#   TOP=~/android/lineage lineage/scripts/setup-tree.sh
# Safe to re-run: copies are refreshed, patches are idempotent.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"     # <repo>/lineage
TOP="${TOP:-$HOME/android/lineage}"
KDTS="$TOP/kernel/amlogic/linux-4.9/arch/arm64/boot/dts/amlogic"
KCFG="$TOP/kernel/amlogic/linux-4.9/arch/arm64/configs"
UBOOT="$TOP/hardware/amlogic/u-boot"
UBOOT_BUILD="$TOP/hardware/amlogic/u-boot_build"

for d in "$TOP/device/amlogic/g12-common" "$KDTS" "$UBOOT/board/amlogic" "$UBOOT_BUILD" "$TOP/vendor/radxa/radxa02pro"; do
    [[ -d "$d" ]] || { echo "missing $d - is the tree synced?" >&2; exit 1; }
done

echo "== device/beelink/galilei"
mkdir -p "$TOP/device/beelink/galilei"
rsync -a --delete --exclude '.git' "$SRC/device/beelink/galilei/" "$TOP/device/beelink/galilei/"
chmod +x "$TOP/device/beelink/galilei/"*.py "$TOP/device/beelink/galilei/build_u-boot.sh"

echo "== build-manifest.xml fallback (git objects may be purged on this host)"
MK="$TOP/vendor/lineage/build/tasks/build-manifest_xml.mk"
if [[ -f "$MK" ]] && ! grep -q 'gen-build-manifest.py' "$MK"; then
    python3 - "$MK" <<'PY'
import sys, re
p = sys.argv[1]
s = open(p).read()
old = '\tpython3 .repo/repo/repo manifest -o - -r | grep -Ev "proprietary_$(MANIFEST_EXCLUDES)" > $@\n'
new = ('\t( python3 .repo/repo/repo manifest -o - -r 2>/dev/null | grep -Ev "proprietary_$(MANIFEST_EXCLUDES)" > $@ ) '
       '|| ( echo "repo manifest failed - using static snapshot" >&2; '
       'python3 device/beelink/galilei/gen-build-manifest.py | grep -Ev "proprietary_$(MANIFEST_EXCLUDES)" > $@ )\n')
assert old in s, "unexpected build-manifest_xml.mk recipe"
open(p, "w").write(s.replace(old, new, 1))
print("   patched", p)
PY
fi

echo "== GApps (MindTheGapps ATV, GAPPS=${GAPPS:-full})"
if [[ "${GAPPS:-full}" == none ]]; then
    rm -rf "$TOP/vendor/mindthegapps-atv"
else
    GZ=$(ls -1 "$SRC"/out/gapps/MindTheGapps-*-arm-ATV-"${GAPPS:-full}"-*.zip 2>/dev/null | sort | tail -1)
    if [[ -n "$GZ" ]]; then
        python3 "$SRC/scripts/make-gapps-vendor.py" "$GZ" "$TOP/vendor/mindthegapps-atv" "$TOP"
    else
        echo "   no MindTheGapps *-arm-ATV-${GAPPS:-full}-*.zip in lineage/out/gapps - vanilla build"
        rm -rf "$TOP/vendor/mindthegapps-atv"
    fi
fi

echo "== kernel patches (lineage/patches/kernel-*.patch, idempotent)"
KSRC="$TOP/kernel/amlogic/linux-4.9"
for kp in "$SRC"/patches/kernel-*.patch; do
    [[ -f "$kp" ]] || continue
    if patch -p1 -d "$KSRC" -R --dry-run -s -f < "$kp" >/dev/null 2>&1; then
        echo "   already applied: $(basename "$kp")"
    elif patch -p1 -d "$KSRC" -N -s -f < "$kp"; then
        echo "   applied: $(basename "$kp")"
    else
        echo "   FAILED to apply $(basename "$kp")" >&2; exit 1
    fi
done

echo "== kernel DTS + config fragment"
cp "$SRC/kernel/dts/g12b_s922x_galilei.dts" "$SRC/kernel/dts/partition_mbox_dynamic_galilei.dtsi" "$KDTS/"
cp "$SRC/kernel/configs/galilei.config" "$KCFG/"
if ! grep -q 'g12b_s922x_galilei.dtb' "$KDTS/Makefile"; then
    sed -i 's|^dtb-y += g12b_a311d_radxa02pro.dtb$|&\ndtb-y += g12b_s922x_galilei.dtb|' "$KDTS/Makefile"
fi
grep -n 'galilei' "$KDTS/Makefile"

echo "== u-boot board g12b_galilei_v1"
python3 "$SRC/uboot/gen_galilei_board.py" "$UBOOT"
cp "$SRC/uboot/build_galilei.sh" "$UBOOT_BUILD/build_galilei.sh"
chmod +x "$UBOOT_BUILD/build_galilei.sh"

echo "== vendor/beelink/galilei skeleton"
V="$TOP/vendor/beelink/galilei"
mkdir -p "$V/proprietary/vendor/lib/egl" "$V/radio"
cp "$TOP/vendor/radxa/radxa02pro/proprietary/vendor/lib/egl/libGLES_mali.so" "$V/proprietary/vendor/lib/egl/"
# misc.img: raw image with the BCB set to boot-recovery (device independent)
cp "$TOP/vendor/radxa/radxa02pro/radio/misc.img" "$V/radio/"
if [[ ! -f "$V/radio/bootloader.img" ]]; then
    # setup-makefiles.py hashes every file in proprietary-firmware.txt, so the bootloader must exist already.
    # Seed it with the prebuilt hybrid candidate (stock Beelink BL2 + LOS FIP); build_u-boot.sh refreshes it later.
    if [[ -f "$SRC/out/u-boot-galilei-hybrid-stockbl2.bin" ]]; then
        cp "$SRC/out/u-boot-galilei-hybrid-stockbl2.bin" "$V/radio/bootloader.img"
        echo "   seeded radio/bootloader.img from lineage/out/u-boot-galilei-hybrid-stockbl2.bin"
    else
        echo "   no bootloader.img and no prebuilt in lineage/out - run device/beelink/galilei/build_u-boot.sh first" >&2
        exit 1
    fi
fi
cd "$TOP/device/beelink/galilei" && ./setup-makefiles.py
ls "$V"

echo "== done. Next: cd $TOP && source build/envsetup.sh && breakfast galilei"
