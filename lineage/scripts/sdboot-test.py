#!/usr/bin/env python3
"""Boot the CoreELEC kernel from the SD card, driven from the u-boot USB burn window.

Why: the box hangs after the u-boot logo with every system on the eMMC. The SD card holds a
CoreELEC image (different bootloader script, kernel 5.x, own dtb) but we cannot tell whether u-boot
ever reaches it, because 'update' enters USB burn mode before it looks at the SD. Here we do the
SD steps by hand and read the status of each one over USB:

    mmcinfo                       -> is the SD card detected at all
    fatload mmc 0 ... kernel.img  -> can u-boot read the FAT partition
    fatload mmc 0 ... dtb.img
    bootm                         -> does u-boot hand over (USB device disappears)

If every step succeeds and the box still shows nothing, a third, independent kernel has died right
after handover, which points at the hardware rather than at any image on the eMMC.

    py -3.14 lineage/scripts/sdboot-test.py [--wait 600]
"""
import argparse, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import amlusb  # noqa: E402
amlusb._prep_dlls()
import usb.core, usb.backend.libusb1 as lb1  # noqa: E402
from diag_common import catch_uboot, cmd_long, read_var, log  # noqa: E402

KERNEL_ADDR = 0x8080000
# CoreELEC cmdline, in < 64 byte pieces (EP0 TPL_CMD limit), joined with hush expansion
ARGS = [
    "BOOT_IMAGE=kernel.img boot=LABEL=COREELEC",
    "disk=LABEL=STORAGE console=ttyS0,115200",
    "no_console_suspend quiet",
]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wait", type=float, default=600)
    ap.add_argument("--no-boot", action="store_true", help="only probe the card, do not bootm")
    ap.add_argument("--extra", action="append", default=[], help="extra bootargs piece (< 40 chars), repeatable; e.g. --extra maxcpus=1")
    a = ap.parse_args()

    dev = catch_uboot(a.wait)
    if dev is None:
        log("no u-boot burn window"); return 2
    log("probe: " + cmd_long(dev, "echo sdtest", 10)[0])

    log("--- SD card")
    st, _ = cmd_long(dev, "mmcinfo", 30)
    log(f"mmcinfo -> {st}   (fails when no SD card is inserted)")
    st, dt = cmd_long(dev, f"fatload mmc 0 0x{KERNEL_ADDR:x} kernel.img", 120)
    log(f"fatload kernel.img -> {st} ({dt:.1f}s)")
    kernel_ok = "success" in st
    log(f"filesize = {read_var(dev, 'filesize')!r} (CoreELEC kernel.img is ~0x20BE000)")
    st, dt = cmd_long(dev, "fatload mmc 0 0x1000000 dtb.img", 60)
    log(f"fatload dtb.img -> {st} ({dt:.1f}s)")
    log(f"filesize = {read_var(dev, 'filesize')!r} (dtb.img is 0x12000)")

    if not kernel_ok:
        log("kernel.img could not be read from the card - nothing to boot"); return 3
    if a.no_boot:
        return 0

    log("--- bootargs")
    cmd_long(dev, "run storeargs", 20)
    for i, piece in enumerate(ARGS, 1):
        cmd_long(dev, f"setenv c{i} '{piece}'", 10)
    extra_refs = ""
    for j, piece in enumerate(a.extra, len(ARGS) + 1):
        cmd_long(dev, f"setenv c{j} '{piece}'", 10)
        extra_refs += f" $c{j}"
        log(f"extra bootarg: {piece}")
    cmd_long(dev, f'setenv bootargs "${{bootargs}} $c1 $c2 $c3{extra_refs}"', 10)

    log("--- bootm (CoreELEC kernel from the SD card)")
    try:
        dev.ctrl_transfer(0x40, 0x30, 0, 1, f"bootm 0x{KERNEL_ADDR:x}\0".encode(), timeout=5000)
    except Exception as e:
        log(f"send bootm: {e}")
    be = lb1.get_backend()
    t0 = time.time()
    while time.time() - t0 < 90:
        time.sleep(1)
        try:
            d = usb.core.find(idVendor=0x1B8E, idProduct=0xC003, backend=be)
        except Exception:
            continue
        if d is None:
            log(f"USB gone after {time.time() - t0:.0f}s -> u-boot handed over to the CoreELEC kernel")
            log("watch the TV: CoreELEC's first boot takes 1-3 minutes (it creates STORAGE on the card)")
            return 0
        try:
            st = bytes(d.ctrl_transfer(0xC0, 0x31, 0, 0, 64, timeout=2000)).split(b"\0", 1)[0].decode("ascii", "replace")
            log(f"bootm status after {time.time() - t0:.0f}s: {st} -> u-boot REFUSED the image")
            return 0
        except Exception:
            pass
    log("bootm: no status and the device is still present after 90 s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
