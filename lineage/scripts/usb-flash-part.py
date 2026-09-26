#!/usr/bin/env python3
"""Write one partition image over USB while the box sits in u-boot burn mode ('update'), then reset.
    py -3.14 usb-flash-part.py --image boot.img [--part boot] [--addr 0x1080000] [--no-reset] [--wait 120]
Seconds instead of a USB Burning Tool run (no whole-package flash, env untouched) or a 25-minute
UART YMODEM. Steps: IDENTIFY (must be u-boot TPL), 'dcache off', writeLargeMemory, 'crc32 -v' against
the file's CRC32 (TPL_STAT reports success/failure; nothing is written on a mismatch),
'store write <part> <addr> 0 <size>', 'reset'. Put the box into burn mode first, e.g. from the u-boot
prompt over UART: 'update' (see night-loop.py). Close the USB Burning Tool (it may hold the device).
"""
import argparse
import importlib.util
import os
import sys
import time
import zlib

here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("uu", os.path.join(here, "uboot-usb.py"))
uu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(uu)


def cmd_wait(dev, cmd, timeout, first=3.0):
    """TPL command whose status is polled until it answers: u-boot does not serve control requests
    while it is busy (crc32 of 64 MiB with dcache off, store write) and they fail with EIO meanwhile.
    Polling every second from the start wedged the burn-mode USB stack in the middle of a 12 MiB
    'store write' (2026-09-26: no answer for 300 s, box needed a power cycle), so the first status
    read waits `first` seconds (the single-shot path waits 3 s and never failed) and polls are 3 s apart."""
    dev.dev.ctrl_transfer(bmRequestType=0x40, bRequest=0x30, wValue=0, wIndex=1,
                          data_or_wLength=cmd.encode("ascii") + b"\0", timeout=5000)
    time.sleep(first)
    end = time.time() + timeout
    last = ""
    while time.time() < end:
        time.sleep(3.0)
        try:
            last = uu.tpl_stat(dev)
        except Exception as e:
            last = f"busy ({e.__class__.__name__})"
            continue
        if "success" in last.lower() or "fail" in last.lower():
            return last
    return last


def verify_ram(dev, addr, blob):
    crc = zlib.crc32(blob) & 0xFFFFFFFF
    res = 0x3000000 if not (addr <= 0x3000000 < addr + len(blob)) else addr + len(blob) + 0x100000
    cmd_wait(dev, f"crc32 0x{addr:x} 0x{len(blob):x} 0x{res:x}", 120)
    got = bytes(dev.readSimpleMemory(res, 4))
    return got in (crc.to_bytes(4, "big"), crc.to_bytes(4, "little")), crc, got


def store_write(dev, part, addr, off, size):
    # eMMC writes run at ~10+ MB/s: wait that long before the first status read
    return cmd_wait(dev, f"store write {part} 0x{addr:x} 0x{off:x} 0x{size:x}", 300,
                    first=3.0 + size / (8 << 20))


def feed(dev):
    """Reload the SoC watchdog (armed from the u-boot prompt before 'update', see box-flash.py) so a
    long but healthy USB session is not reset, while a wedged one still is."""
    try:
        uu.tpl_cmd(dev, "mw.l 0xffd0f0dc 0", wait=0.2)
    except Exception:
        pass


def chunked(dev, a, data):
    """Big images (vendor 512 MiB) in RAM-sized pieces: upload, CRC check, store write at offset."""
    total = len(data); t0 = time.time()
    for off in range(0, total, a.chunk):
        feed(dev)
        blob = data[off:off + a.chunk]
        blob += b"\0" * (-len(blob) % 4096)
        dev.writeLargeMemory(a.addr, blob, 4096)
        ok, crc, got = verify_ram(dev, a.addr, blob)
        if not ok:
            uu.log(f"chunk @0x{off:x}: CRC mismatch ({got.hex()} vs {crc:08x}) - stopping")
            return 4
        r = store_write(dev, a.part, a.addr, off, len(blob))
        uu.log(f"chunk @0x{off:x} ({len(blob) >> 20} MiB): crc ok, store write -> {r}")
        if "success" not in r.lower():
            return 5
    uu.log(f"{a.part}: {total >> 20} MiB written in {time.time() - t0:.0f}s")
    if not a.no_reset:
        uu.log("reset")
        try:
            dev.tplCommand(1, b"reset\0")
        except Exception as e:
            uu.log(f"(expected) link dropped: {e}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk", type=lambda x: int(x, 0), default=8 << 20,
                    help="images bigger than this go in pieces (default 12 MiB: a 64 MiB piece at "
                         "0x1080000 overwrote the burn-mode u-boot's own buffers and wedged it)")
    ap.add_argument("--image", required=True)
    ap.add_argument("--part", default="boot")
    ap.add_argument("--addr", type=lambda x: int(x, 0), default=0x1080000)
    ap.add_argument("--no-reset", action="store_true")
    ap.add_argument("--wait", type=float, default=120)
    a = ap.parse_args()
    data = open(a.image, "rb").read()
    size = len(data)
    crc = zlib.crc32(data) & 0xFFFFFFFF
    padded = data + b"\0" * (-size % 4096)
    uu.log(f"{a.image}: {size} bytes, crc32 {crc:08x} -> {a.part}")
    uu.WAIT_FRESH[0] = False
    if not uu.wait_device(a.wait):
        uu.log("no USB burn-mode device"); return 2
    dev = uu.pyamlboot.AmlogicSoC()
    ident = []
    for _ in range(8):   # libusb0.sys sometimes returns a truncated IDENTIFY (1 byte); retry
        try:
            ident = [ord(c) for c in dev.identify()]
        except Exception as e:
            uu.log(f"identify: {e}")
        if len(ident) >= 4:
            break
        time.sleep(0.4)
    if len(ident) < 4 or ident[3] != 16:
        uu.log(f"not u-boot burn mode (identify {ident})"); return 3
    uu.log("alive -> " + uu.tpl_cmd(dev, "echo galilei-usb-flash"))
    uu.log("dcache off -> " + uu.tpl_cmd(dev, "dcache off"))
    feed(dev)
    if size > a.chunk and a.part not in ("dtb", "_aml_dtb"):
        return chunked(dev, a, data)
    t0 = time.time()
    dev.writeLargeMemory(a.addr, padded, 4096)
    uu.log(f"upload {size} B in {time.time() - t0:.1f}s")
    # 'crc32 -v' is not built into this u-boot and burn mode shows no command output: let u-boot
    # store the CRC in RAM ('crc32 <addr> <count> <resaddr>') and read those 4 bytes back over USB
    res = 0x3000000
    r = uu.tpl_cmd(dev, f"crc32 0x{a.addr:x} 0x{size:x} 0x{res:x}", wait=2.0)
    got = bytes(dev.readSimpleMemory(res, 4))
    ok = got in (crc.to_bytes(4, "big"), crc.to_bytes(4, "little"))
    uu.log(f"crc32 -> {r}; RAM crc {got.hex()} vs file {crc:08x}: {'OK' if ok else 'MISMATCH'}")
    if not ok:
        uu.log("CRC mismatch - nothing written")
        return 4
    t1 = time.time()
    if a.part in ("dtb", "_aml_dtb"):
        # the kernel's DTB comes from here (u-boot loads _aml_dtb to dtb_mem_addr), NOT from the
        # boot.img DTB section; the reserved dtb area has its own store sub-command
        wcmd = f"store dtb write 0x{a.addr:x} 0x{size:x}"
    else:
        wcmd = f"store write {a.part} 0x{a.addr:x} 0 0x{size:x}"
    r = uu.tpl_cmd(dev, wcmd, wait=3.0)
    for _ in range(60):          # the write may still be running when the first status is read
        if "success" in r.lower() or "fail" in r.lower():
            break
        time.sleep(1); r = uu.tpl_stat(dev)
    uu.log(f"store write {a.part} -> {r} ({time.time() - t1:.1f}s)")
    if "success" not in r.lower():
        return 5
    if not a.no_reset:
        uu.log("reset")
        try:
            dev.tplCommand(1, b"reset\0")
        except Exception as e:
            uu.log(f"(expected) link dropped: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
