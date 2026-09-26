#!/usr/bin/env bash
# v2: compile the galilei DTB against voodik's kernel tree (its mesong12b.dtsi and dt-bindings), with
# the v2 partition table (plain system/vendor/product/odm) and first-stage fstab.
#   bash lineage/scripts/v2-build-dtb.sh            (WSL) -> ~/v2/out/g12b_s922x_galilei_v2.dtb (+ .dts dump)
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../kernel/dts" && pwd)"
K=$HOME/v2/kernel-voodik
OUT=$HOME/v2/out
mkdir -p "$OUT"
W=$(mktemp -d)
cp "$SRC"/v2/*.dts* "$W"/
D=$K/arch/arm64/boot/dts
cpp -nostdinc -undef -D__DTS__ -x assembler-with-cpp \
    -I "$W" -I "$D/amlogic" -I "$D" -I "$K/include" \
    "$W/g12b_s922x_galilei_v2.dts" -o "$W/pre.dts"
DTC=$(command -v dtc)
[ -x "$HOME/v2/kout/scripts/dtc/dtc" ] && DTC=$HOME/v2/kout/scripts/dtc/dtc
"$DTC" -I dts -O dtb -b 0 -@ -o "$OUT/g12b_s922x_galilei_v2.dtb" "$W/pre.dts" 2> "$OUT/dtc-warnings.txt" \
    || { cat "$OUT/dtc-warnings.txt" | grep -v -i warning | head -30; exit 1; }
"$DTC" -I dtb -O dts -o "$OUT/g12b_s922x_galilei_v2.dump.dts" "$OUT/g12b_s922x_galilei_v2.dtb" 2>/dev/null
rm -rf "$W"
echo "dtb: $(stat -c %s "$OUT/g12b_s922x_galilei_v2.dtb") bytes, dtc warnings: $(grep -c -i warning "$OUT/dtc-warnings.txt")"
