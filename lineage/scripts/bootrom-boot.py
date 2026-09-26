#!/usr/bin/env python3
"""RAM-boot a packed Amlogic bootloader (u-boot.bin = BL2 + FIP) from BootROM USB mode.
Nothing is written to eMMC. Works with the libusb0 (Burning Tool) or WinUSB driver.

    py -3.14 bootrom-boot.py <u-boot.bin>
e.g. the stock Beelink bootloader (lineage/out/u-boot-stock-beelink.bin) as a control test, or a
galilei candidate. Box must show IDENTIFY Stage 0.0 (BootROM): power on with the USB-A<->USB-A
cable attached to the USB 2.0 port (this box then waits in BootROM USB mode - "red eyes").
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from amlusb import open_soc, describe  # noqa: E402


def log(m):
    print(time.strftime("%H:%M:%S") + " " + m, flush=True)


def main():
    if len(sys.argv) != 2:
        print(__doc__); return 2
    path = sys.argv[1]
    data = open(path, "rb").read()
    soc, be = open_soc()
    log(f"backend {be}: {describe(soc.ident)}")
    if soc.ident[3] == 8:
        log("BL2 already running (Stage x.8) - continuing with the AMLC upload of the same image")
    else:
        if soc.ident[3] != 0:
            log("not BootROM stage - refusing (use uboot-usb.py / chainload-test.py for u-boot burn mode)")
            return 3
        if soc.ident[4] and not soc.ident[5]:
            log("BootROM wants a password (secure boot) - cannot RAM-boot")
            return 4
        log(f"writing BL2 (first 64 KiB of {os.path.basename(path)}, {len(data)} bytes total) to 0xfffa0000")
        soc.writeLargeMemory(0xFFFA0000, data[0:0x10000], 4096)
        log("run 0xfffa0000")
        soc.run(0xFFFA0000)
        # BL2 brings up its own USB stack: on Windows the device re-enumerates and the old handle dies.
        # Re-open it (expect Stage x.8 = BL2 asking for the rest of the image via AMLC).
        soc = None
        for i in range(20):
            time.sleep(0.5)
            try:
                soc, be = open_soc()
                if soc.ident[3] == 8:
                    break
                log(f"re-open: {describe(soc.ident)} (waiting for BL2 stage)")
            except Exception:
                soc = None
        if soc is None or soc.ident[3] != 8:
            log("BL2 did not come up over USB (no Stage x.8) - DDR init failed or BL2 rejected; power-cycle the box")
            return 5
        log(f"BL2 up: {describe(soc.ident)}")
    prev = (-1, -1); seq = 0
    while True:
        try:
            length, offset = soc.getBootAMLC()
        except Exception as e:
            log(f"AMLC request failed ({e}) - BL2 may have finished or dropped USB")
            return 5
        if (length, offset) == prev:
            log("[BL2 END] - BL2 handed over to BL30/BL31/BL33 (watch HDMI / network)")
            break
        prev = (length, offset)
        log(f"AMLC dataSize={length} offset={offset} seq={seq}")
        soc.writeAMLCData(seq, offset, data[offset:offset + length])
        seq += 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
