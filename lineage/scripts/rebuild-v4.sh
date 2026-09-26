#!/usr/bin/env bash
# 2026-09-24: BL33 v4 (CONFIG_GALILEI_FIXED_BOOTENV: compiled preboot/bootcmd, env ones ignored) and the
# chainload+stockbl package with the multi-DTB (galilei + stock w400_b carrying the LOS partition table).
# No Android rebuild (nothing changed in LOS). Run inside WSL:
#   bash /mnt/c/<path-to-repo>/lineage/scripts/rebuild-v4.sh
set -o pipefail
export PATH="$HOME/bin:$PATH"
TOP="${TOP:-$HOME/android/lineage}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"          # <repo>/lineage
UB="$TOP/hardware/amlogic/u-boot"
step() { echo "=== $(date '+%F %T') $*"; }
step "rebuild-v4 start"
python3 "$SRC/uboot/gen_galilei_board.py" "$UB" || { step "gen_galilei_board FAILED"; exit 1; }
grep -q "CONFIG_GALILEI_FIXED_BOOTENV 1" "$UB/board/amlogic/configs/g12b_galilei_v1.h" || { step "config .h lacks the v4 switch"; exit 1; }
grep -q "CONFIG_GALILEI_FIXED_BOOTENV" "$UB/common/main.c" "$UB/common/autoboot.c" || { step "common/ not patched"; exit 1; }
grep -q 'setenv("preboot"' "$UB/board/amlogic/g12b_galilei_v1/g12b_galilei_v1.c" && { step "board .c still has the v3 setenv(preboot)"; exit 1; }
step "u-boot build (BL33 v4)"
bash "$TOP/device/beelink/galilei/build_u-boot.sh" || { step "u-boot build FAILED"; exit 1; }
BIN="$UB/build/u-boot.bin"; ls -la "$BIN"
python3 - "$BIN" "$SRC/out/bl33-v4.img" <<'PY'
import sys, zlib
d = open(sys.argv[1], "rb").read()
assert len(d) <= 0x140000, "BL33 larger than the 0x140000 read in the preboot hook"
assert b"forceupdate" in d and b"run bcb_cmd; run factory_reset_poweroff_protect;run upgrade_check;run init_display;run storeargs;forceupdate;" in d
d += b"\0" * (-len(d) % 4096)
open(sys.argv[2], "wb").write(d); print("bl33-v4.img", len(d), "bytes crc32 %08x" % zlib.crc32(d))
PY
[[ -f "$SRC/out/bl33-v4.img" ]] || { step "bl33-v4.img not written"; exit 1; }
step "package chainload+stockbl+multidtb2-v4"
DTBIMG="$SRC/out/multi-dtb-galilei+w400b-losparts.img" OUT_SUFFIX="+multidtb2-v4" ONLY_CHAINLOAD=1 TOP="$TOP" \
    bash "$SRC/scripts/make-packages-with-bootloader.sh" 2>&1 | grep -E "dtb.img <-|bl33.img|Size=|Install image|DONE|rror" || { step "package FAILED"; exit 1; }
step "rebuild-v4 end"
