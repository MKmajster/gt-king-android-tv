#!/usr/bin/env bash
# v2: multi-DTB for the _aml_dtb item = stock g12b_w400_b (for the stock u-boot's own board init and
# the burn-time partition table) with the v2 partition table + our galilei v2 DTB (for the kernel).
#   bash lineage/scripts/v2-make-multidtb.sh      (WSL; needs ~/v2/out/g12b_s922x_galilei_v2.dtb)
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT=$HOME/v2/out
W=$(mktemp -d)
dtc -I dtb -O dts -o "$W/w400b.dts" "$SRC/out/stock-w400_b.dtb" 2>/dev/null
python3 - "$W/w400b.dts" "$SRC/kernel/dts/v2/partition_mbox_v2_galilei.dtsi" "$W/w400b-v2.dts" <<'EOF'
import re, sys
dts, part, out = sys.argv[1:4]
s = open(dts).read()
i = s.find("\tpartitions {")
assert i > 0, "no partitions node in stock w400_b"
depth = 0; j = s.index("{", i)
while True:
    c = s[j]
    if c == "{": depth += 1
    elif c == "}":
        depth -= 1
        if depth == 0: break
    j += 1
end = s.index(";", j) + 1
s = s[:i] + s[end:]
p = open(part).read()
p = p[p.index("partitions: partitions{"):]
p = p[:p.rindex("};/* end of / */")]
s += "\n/ {\n\t" + p + "};\n"
open(out, "w").write(s)
print("partitions replaced")
EOF
dtc -I dts -O dtb -o "$OUT/stock-w400_b+v2parts.dtb" "$W/w400b-v2.dts" 2>/dev/null
python3 "$SRC/scripts/make-multi-dtb.py" "$OUT/multi-dtb-v2.img" "$OUT/g12b_s922x_galilei_v2.dtb" "$OUT/stock-w400_b+v2parts.dtb"
for f in "$OUT/stock-w400_b+v2parts.dtb" "$OUT/g12b_s922x_galilei_v2.dtb"; do
    echo "$(basename "$f"): $(fdtget "$f" /partitions parts) parts: $(for k in $(seq 0 30); do n=$(fdtget -t s "$f" /partitions part-$k 2>/dev/null) || break; done; fdtget -l "$f" /partitions | tr '\n' ' ')"
done
rm -rf "$W"
