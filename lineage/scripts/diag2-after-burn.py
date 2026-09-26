#!/usr/bin/env python3
"""Second diagnostics pass from the u-boot burn window (see diag-after-burn.py for the transport).
The stock storeboot is:  if imgread kernel boot 1080000; then bootm 1080000; fi; run storeargs; run update
and the box lands in 'update' (burn window) after the logo -> either imgread or bootm fails inside
u-boot, before any kernel code runs. Split it up and test each piece by its USB status:
  1. store dtb read + aml_dt (multi-dtb recognised? bootm needs aml_dt to pick the dtb)
  2. imgread kernel boot / recovery (image header, secure-boot check)
  3. DDR: fill two regions with a pattern and cmp.l them (mtest is not available in this u-boot)
  4. optionally 'bootm 1080000': if the kernel starts, the USB device vanishes; if u-boot refuses,
     the status says failed and the box stays in the burn window
    py -3.14 lineage/scripts/diag2-after-burn.py [--bootm] [--skip-ddr]
Close USB_Burning_Tool yourself as soon as it says Burning successfully (it runs elevated).
"""
import argparse, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import amlusb  # noqa: E402
amlusb._prep_dlls()
import usb.core, usb.backend.libusb1 as lb1  # noqa: E402
from diag_common import catch_uboot, cmd_long, read_var, log  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wait", type=float, default=1800)
    ap.add_argument("--bootm", action="store_true", help="finally try 'bootm 1080000' and watch whether u-boot hands over")
    ap.add_argument("--skip-ddr", action="store_true")
    a = ap.parse_args()

    dev = catch_uboot(a.wait)
    if dev is None:
        log("no u-boot burn window"); return 2
    log("probe: " + cmd_long(dev, "echo diag2", 10)[0])

    log("--- 1. dtb")
    log(f"aml_dt before = {read_var(dev, 'aml_dt')!r}")
    st, dt = cmd_long(dev, "store dtb read 0x1000000", 30)
    log(f"store dtb read 0x1000000 -> {st} ({dt:.1f}s)")
    log(f"aml_dt after  = {read_var(dev, 'aml_dt')!r}   (stock multi-dtb should give g12b_w400_b)")
    for v in ("loadaddr", "boot_part", "avb2", "lock", "system_mode", "active_slot", "upgrade_step"):
        log(f"env {v} = {read_var(dev, v)!r}")

    log("--- 2. imgread")
    for c in ("imgread kernel boot 1080000", "imgread kernel recovery 1080000", "imgread dtb boot 1000000"):
        st, dt = cmd_long(dev, c, 60)
        log(f"{c} -> {st} ({dt:.1f}s)")

    if not a.skip_ddr:
        log("--- 3. DDR (mw.l pattern into two regions, cmp.l)")
        # u-boot itself lives at the top of the first 2 GiB (relocation, malloc, stack): stay below 0x60000000
        # there; the 2..4 GiB half is tested last because a missing MMU mapping there would abort u-boot.
        low = (0x10000000, 0x38000000, 0x28000000)
        for pat in ("0xa5a5a5a5", "0x5a5a5a5a", "0x00000000", "0xffffffff"):
            a1, a2, n = low
            words = n // 4
            st1, d1 = cmd_long(dev, f"mw.l 0x{a1:x} {pat} 0x{words:x}", 600)
            st2, d2 = cmd_long(dev, f"mw.l 0x{a2:x} {pat} 0x{words:x}", 600)
            st3, d3 = cmd_long(dev, f"cmp.l 0x{a1:x} 0x{a2:x} 0x{words:x}", 600)
            log(f"DDR {pat}: fill 0x{a1:08x} {st1} ({d1:.0f}s), fill 0x{a2:08x} {st2} ({d2:.0f}s), cmp.l {n >> 20} MiB -> {st3} ({d3:.0f}s)")
            if "success" not in st3:
                log("DDR: MISMATCH -> bad RAM somewhere in 0x10000000-0x60000000")
        log("DDR: upper half 0x80000000-0xE0000000 (2..4 GiB)")
        for a1, a2, n in ((0x80000000, 0xB0000000, 0x30000000),):
            words = n // 4
            st1, d1 = cmd_long(dev, f"mw.l 0x{a1:x} 0xa5a5a5a5 0x{words:x}", 600)
            st2, d2 = cmd_long(dev, f"mw.l 0x{a2:x} 0xa5a5a5a5 0x{words:x}", 600)
            st3, d3 = cmd_long(dev, f"cmp.l 0x{a1:x} 0x{a2:x} 0x{words:x}", 600)
            log(f"DDR high: fill {st1} ({d1:.0f}s), fill {st2} ({d2:.0f}s), cmp.l {n >> 20} MiB -> {st3} ({d3:.0f}s)")

    if a.bootm:
        log("--- 4. bootm 1080000 (after imgread kernel boot)")
        cmd_long(dev, "imgread kernel boot 1080000", 60)
        try:
            dev.ctrl_transfer(0x40, 0x30, 0, 1, b"bootm 1080000\0", timeout=5000)
        except Exception as e:
            log(f"send bootm: {e}")
        t0 = time.time()
        be = lb1.get_backend()
        while time.time() - t0 < 60:
            time.sleep(1)
            try:
                d = usb.core.find(idVendor=0x1B8E, idProduct=0xC003, backend=be)
                if d is None:
                    log(f"USB device gone after {time.time() - t0:.0f}s -> u-boot handed over to the kernel (bootm accepted)")
                    return 0
                st = bytes(d.ctrl_transfer(0xC0, 0x31, 0, 0, 64, timeout=2000)).split(b"\0", 1)[0].decode("ascii", "replace")
                log(f"bootm status after {time.time() - t0:.0f}s: {st} -> u-boot REFUSED to boot the image")
                return 0
            except Exception:
                pass
        log("bootm: no status and device still present after 60 s")
    log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
