#!/usr/bin/env python3
"""Kernel console without UART: read the stock kernel's ramoops/pstore region out of DDR from the
u-boot USB burn window and print the last console lines (persistent_ram zones, signature "DBGC").

Stock GT-King: ramoops @ 0x07400000, 1 MiB (live.dts reserved-memory), console zone 0x4000 (cmdline
ramoops.console_size). DDR keeps its contents across a warm reset and usually across a power cut of
well under a second, so: box hung after the logo -> hold the pinhole -> unplug/replug power as fast
as possible -> stock u-boot 'forceupdate' -> burn window -> this script (IDENTIFY clears the timeout).

    py -3.14 lineage/scripts/read-ramoops.py [--wait 300] [--base 0x07400000] [--size 0x100000] [--raw out.bin]
Every read is a 64-byte EP0 control transfer (wValue = addr>>16, wIndex = addr&0xffff): ~1 MiB/min.
"""
import argparse, os, re, struct, sys, time, zlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import amlusb  # noqa: E402
amlusb._prep_dlls()
import usb.core, usb.backend.libusb1 as lb1  # noqa: E402

VID, PID = 0x1B8E, 0xC003
SIG = 0x43474244  # "DBGC" persistent_ram_buffer signature (little endian)


def log(m):
    print(time.strftime("%H:%M:%S") + " " + m, flush=True)


def read_mem(dev, base, size, save_to=None):
    """64-byte control reads; a chunk that keeps failing is filled with 0x00 and counted (a partial
    dump is still useful: the console zone is only a few dozen KiB of the 1 MiB region)."""
    out = bytearray()
    addr = base
    t0 = time.time()
    bad = 0
    while addr < base + size:
        chunk = None
        for _ in range(8):
            try:
                chunk = bytes(dev.ctrl_transfer(0xC0, 0x02, addr >> 16, addr & 0xFFFF, 64, timeout=3000))
                if len(chunk) == 64:
                    break
            except Exception:
                time.sleep(0.15)
        if not chunk or len(chunk) != 64:
            bad += 1
            chunk = bytes(64)
            if bad % 50 == 1:
                log(f"  read hole at 0x{addr:08x} (holes so far: {bad})")
        out += chunk
        addr += 64
        if len(out) % 0x20000 == 0:
            log(f"  {len(out) // 1024} KiB ... ({len(out) / (time.time() - t0) / 1024:.0f} KiB/s, holes {bad})")
            if save_to:
                open(save_to, "wb").write(bytes(out))
    log(f"read done: {len(out)} bytes, {bad} unreadable 64-byte chunks")
    return bytes(out)


def zones(buf, base):
    """Yield (offset, start, size, data) for every persistent_ram zone found in buf."""
    for m in re.finditer(struct.pack("<I", SIG), buf):
        off = m.start()
        if off + 12 > len(buf):
            continue
        start, size = struct.unpack_from("<II", buf, off + 4)
        if size == 0 or size > 0x100000 or off + 12 + size > len(buf):
            continue
        data = buf[off + 12: off + 12 + size]
        # ring buffer: 'start' is the write pointer -> oldest data begins there
        data = data[start:] + data[:start]
        yield base + off, start, size, data


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wait", type=float, default=300)
    ap.add_argument("--base", type=lambda s: int(s, 0), default=0x07400000)
    ap.add_argument("--size", type=lambda s: int(s, 0), default=0x100000)
    ap.add_argument("--raw", default="lineage/out/ramoops-%s.bin" % time.strftime("%Y%m%d-%H%M%S"))
    ap.add_argument("--reset", action="store_true", help="u-boot 'reset' after reading")
    a = ap.parse_args()

    be = lb1.get_backend()
    deadline = time.time() + a.wait
    log(f"polling for {VID:04x}:{PID:04x} burn window (up to {a.wait:.0f}s) ...")
    dev = None
    while time.time() < deadline:
        try:
            dev = usb.core.find(idVendor=VID, idProduct=PID, backend=be)
        except Exception:
            dev = None
        if dev is None:
            time.sleep(0.15)
            continue
        try:
            b = bytes(dev.ctrl_transfer(0xC0, 0x20, 0, 0, 8, timeout=1500))
        except Exception:
            time.sleep(0.15)
            continue
        if len(b) >= 8:
            log(f"caught: {amlusb.describe(b)}")
            if b[3] != 16:
                log("BootROM/BL2 stage, not u-boot - RAM read would be wrong; keep polling")
                time.sleep(0.5)
                continue
            break
        dev = None
    if dev is None:
        log("no burn window"); return 2

    log(f"reading 0x{a.size:x} bytes @ 0x{a.base:08x}")
    buf = read_mem(dev, a.base, a.size, a.raw)
    open(a.raw, "wb").write(buf)
    log(f"saved {a.raw}")
    nz = sum(1 for x in buf if x)
    log(f"non-zero bytes: {nz} / {len(buf)}")
    found = 0
    for off, start, size, data in zones(buf, a.base):
        found += 1
        txt = data.decode("utf-8", "replace")
        printable = sum(1 for c in txt if c.isprintable() or c in "\r\n\t") / max(len(txt), 1)
        log(f"--- zone @ 0x{off:08x} start={start} size={size} printable={printable:.0%}")
        if printable > 0.8:
            lines = [l for l in txt.replace("\r", "").split("\n") if l.strip()]
            print("\n".join(lines[-80:]))
        else:
            try:
                dec = zlib.decompress(data)
                print(dec.decode("utf-8", "replace")[-6000:])
            except Exception:
                print(f"(binary/compressed zone, {size} bytes)")
    if not found:
        log("no persistent_ram zones found: RAM did not survive the power cut, or the kernel never started ramoops")
    if a.reset:
        try:
            dev.ctrl_transfer(0x40, 0x30, 0, 1, b"reset\0", timeout=5000)  # TPL_CMD, as in catch-burn.py
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
