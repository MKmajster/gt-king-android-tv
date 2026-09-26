#!/usr/bin/env bash
# Unpack vendor (and optionally system) from voodik's block-based LineageOS OTA zip for ODROID-N2
# (S922X, arm64 userspace) - the donor for 64-bit Mali/gralloc blobs.
#   bash lineage/scripts/extract-voodik-vendor.sh <ota.zip> [vendor|system ...]
# Output: ~/voodik/<part>.img and ~/voodik/<part>/ (files, via debugfs or fsck.erofs; NOFILES=1 skips
# the file dump and keeps only the image)
set -euo pipefail
ZIP=$1; shift
PARTS=${*:-vendor}
TOP=${TOP:-$HOME/android/lineage}
BIN=$TOP/out/host/linux-x86/bin
W=$HOME/voodik
mkdir -p "$W"
cd "$W"

sdat2img() {  # transfer.list new.dat out.img
    python3 - "$1" "$2" "$3" <<'EOF'
import sys
tl, dat, out = sys.argv[1:4]
lines = open(tl).read().split("\n")
version = int(lines[0])
cmds = lines[4:] if version >= 2 else lines[2:]
BS = 4096
with open(dat, "rb") as src, open(out, "wb") as dst:
    maxblk = 0
    for c in cmds:
        if not c.strip():
            continue
        op, rng = c.split(" ", 1)
        nums = [int(x) for x in rng.split(",")]
        pairs = list(zip(nums[1::2], nums[2::2]))
        if op == "new":
            for a, b in pairs:
                dst.seek(a * BS)
                dst.write(src.read((b - a) * BS))
                maxblk = max(maxblk, b)
        elif op in ("zero", "erase"):
            for a, b in pairs:
                maxblk = max(maxblk, b)
    dst.truncate(maxblk * BS)
print("wrote", out)
EOF
}

for p in $PARTS; do
    unzip -o -q "$ZIP" "$p.new.dat.br" "$p.transfer.list"
    B=$(command -v brotli || echo "$BIN/brotli")
    "$B" -d -f "$p.new.dat.br" -o "$p.new.dat"
    sdat2img "$p.transfer.list" "$p.new.dat" "$p.img"
    rm -f "$p.new.dat" "$p.new.dat.br"
    [ "${NOFILES:-0}" = 1 ] && { echo "$p: $(file -b "$p.img" | cut -c1-60)"; continue; }
    rm -rf "$p"; mkdir -p "$p"
    if file "$p.img" | grep -qi "ext[234]"; then
        debugfs -R "rdump / $W/$p" "$p.img" >/dev/null 2>&1
    else
        "$BIN/fsck.erofs" --extract="$W/$p" "$p.img" >/dev/null
    fi
    echo "$p: $(file -b "$p.img" | cut -c1-60), $(find "$p" -type f | wc -l) files"
done
