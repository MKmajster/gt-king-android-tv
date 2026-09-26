#!/usr/bin/env python3
"""Restore the whole 'reserved' partition from the 14.09 backup of this box, over USB, from the
u-boot burn window.

Why: 'reserved' holds far more than the dtb. In the 14.09 image of this box there is the MPT
partition table at 0x0, a 0xaa55 pattern block at 0x300000, the multi-dtb at 0x400000 (two copies),
an 0xff00 block at 0x600000, a block of random data at 0x700000 (secure storage) and an 'IEcfg'
block at 0x800000. Our LineageOS package rewrote only _aml_dtb, and the USB Burning Tool ran ERASE
FLASH/ERASE BOOTLOADER before that - anything else in the partition is whatever survived. Restoring
the exact original content is the last software step that can still change the box's behaviour.

The upload uses the bulk path (pyamlboot writeLargeMemory, ~3 MB/s), not 64-byte control transfers,
and is written back in 8 MiB chunks so progress is visible and DDR use stays low.

    py -3.14 lineage/scripts/restore-reserved.py [--wait 600] [--img backup/20260914-stock/reserved.img]
The box must be in the u-boot burn window (pinhole at power-on with the A-A cable connected).
"""
import argparse, hashlib, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import amlusb  # noqa: E402
amlusb._prep_dlls()
from pyamlboot import pyamlboot  # noqa: E402
from diag_common import catch_uboot, cmd_long, read_var, log  # noqa: E402

LOAD = 0x10000000
CHUNK = 0x800000  # 8 MiB


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wait", type=float, default=600)
    ap.add_argument("--img", default="backup/20260914-stock/reserved.img")
    ap.add_argument("--dry-run", action="store_true", help="upload and verify the RAM copy, do not write the eMMC")
    a = ap.parse_args()

    data = open(a.img, "rb").read()
    log(f"{a.img}: {len(data)} bytes, sha1 {hashlib.sha1(data).hexdigest()}")
    assert len(data) % CHUNK == 0, "image size must be a multiple of 8 MiB"

    dev = catch_uboot(a.wait)
    if dev is None:
        log("no u-boot burn window"); return 2
    log("probe: " + cmd_long(dev, "echo restore", 10)[0])
    log(f"aml_dt before = {read_var(dev, 'aml_dt')!r}")

    soc = pyamlboot.AmlogicSoC.__new__(pyamlboot.AmlogicSoC)
    soc.dev = dev
    t0 = time.time()
    for off in range(0, len(data), CHUNK):
        part = data[off:off + CHUNK]
        cmd_long(dev, "dcache off", 10)
        soc.writeLargeMemory(LOAD, part, 4096)
        head = b""
        try:
            head = bytes(dev.ctrl_transfer(0xC0, 0x02, LOAD >> 16, LOAD & 0xFFFF, 64, timeout=3000))
        except Exception:
            pass
        if head and head != part[:64]:
            log(f"upload MISMATCH at 0x{off:08x} - aborting without writing"); return 3
        if a.dry_run:
            log(f"0x{off:08x}: uploaded {len(part)} bytes, head OK (dry run)")
            continue
        st, dt = cmd_long(dev, f"store write reserved 0x{LOAD:x} 0x{off:x} 0x{CHUNK:x}", 300)
        log(f"0x{off:08x}/0x{len(data):08x}: store write -> {st} ({dt:.1f}s, {time.time() - t0:.0f}s total)")
        if "success" not in st:
            log("write failed - stopping"); return 4

    if a.dry_run:
        return 0
    log("--- verify")
    st, _ = cmd_long(dev, "store dtb read 0x1000000", 30)
    log(f"store dtb read -> {st}")
    log(f"aml_dt after = {read_var(dev, 'aml_dt')!r}   (expected g12b_w400_b)")
    st, _ = cmd_long(dev, "imgread kernel boot 1080000", 60)
    log(f"imgread kernel boot -> {st}")
    log("done - power-cycle the box and watch the TV")
    return 0


if __name__ == "__main__":
    sys.exit(main())
