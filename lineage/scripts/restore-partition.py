#!/usr/bin/env python3
"""Restore an eMMC partition from a backup image over USB, from the u-boot burn window.

'store write <part> <addr> <off> <size>' in this u-boot refuses sizes above a few KiB at offset 0 of
'reserved' (the MPT partition table area is managed by u-boot itself), but accepts 1 MiB writes at
higher offsets, so the image is written in 1 MiB chunks and the refused range is reported, not forced.
Each chunk is uploaded with the bulk path (pyamlboot writeLargeMemory) and its first 64 bytes are
read back before the write.

    py -3.14 lineage/scripts/restore-partition.py reserved backup/20260914-stock/reserved.img [--start 0x300000]
    py -3.14 lineage/scripts/restore-partition.py logo backup/20260914-stock/logo.img
"""
import argparse, hashlib, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import amlusb  # noqa: E402
amlusb._prep_dlls()
from pyamlboot import pyamlboot  # noqa: E402
from diag_common import catch_uboot, cmd_long, read_var, log  # noqa: E402

LOAD = 0x10000000
CHUNK = 0x100000  # 1 MiB: the largest size this u-boot accepted for 'store write'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("part")
    ap.add_argument("img")
    ap.add_argument("--start", type=lambda s: int(s, 0), default=0)
    ap.add_argument("--end", type=lambda s: int(s, 0), default=None)
    ap.add_argument("--wait", type=float, default=600)
    a = ap.parse_args()

    data = open(a.img, "rb").read()
    end = a.end if a.end is not None else len(data)
    log(f"{a.img}: {len(data)} bytes, sha1 {hashlib.sha1(data).hexdigest()}")
    log(f"restoring {a.part} 0x{a.start:x}..0x{end:x} in {CHUNK >> 20} MiB chunks")

    dev = catch_uboot(a.wait)
    if dev is None:
        log("no u-boot burn window"); return 2
    log("probe: " + cmd_long(dev, "echo restore", 10)[0])

    soc = pyamlboot.AmlogicSoC.__new__(pyamlboot.AmlogicSoC)
    soc.dev = dev
    t0 = time.time()
    written = refused = 0
    for off in range(a.start, end, CHUNK):
        part = data[off:off + CHUNK]
        if len(part) < CHUNK:
            part = part + b"\0" * (CHUNK - len(part))
        cmd_long(dev, "dcache off", 10)
        soc.writeLargeMemory(LOAD, part, 4096)
        try:
            head = bytes(dev.ctrl_transfer(0xC0, 0x02, LOAD >> 16, LOAD & 0xFFFF, 64, timeout=3000))
            if head and head != part[:64]:
                log(f"0x{off:08x}: upload MISMATCH - skipping this chunk"); refused += 1; continue
        except Exception:
            pass
        st, dt = cmd_long(dev, f"store write {a.part} 0x{LOAD:x} 0x{off:x} 0x{CHUNK:x}", 300)
        if "success" in st:
            written += 1
        else:
            refused += 1
            log(f"0x{off:08x}: store write -> {st}")
        if (off // CHUNK) % 8 == 0:
            log(f"0x{off:08x}/0x{end:08x}  written {written}, refused {refused}  ({time.time() - t0:.0f}s)")
    log(f"done: {written} chunks written, {refused} refused, {time.time() - t0:.0f}s")

    st, _ = cmd_long(dev, "store dtb read 0x1000000", 30)
    log(f"store dtb read -> {st}; aml_dt = {read_var(dev, 'aml_dt')!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
