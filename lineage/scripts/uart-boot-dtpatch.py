#!/usr/bin/env python3
"""Boot the flashed boot.img once with in-RAM DTB edits, from the galilei u-boot prompt (no flash).
    py -3.14 uart-boot-dtpatch.py --port COM9 --bootimg <the flashed boot.img, local copy>
        --set "/sdio@ffe03000 status okax" [--set ...] [--args "initcall_debug ignore_loglevel"]
Catches the galilei prompt (Ctrl-C; via 'run preboot' if the stock one is caught first), then:
  imgread kernel boot <loadaddr>          (the whole boot image into RAM)
  fdt addr <loadaddr + dtb offset>         (the DTB section of the header-v2 image, computed here)
  fdt set <path> <prop> <value>            (each --set; the value must keep the old length - the blob
                                            has no free space - e.g. status "okay" -> "okax" = disabled)
  run storeargs; setenv bootargs ${bootargs} rootfstype=ramfs <args>; bootm <loadaddr>
Nothing is written to the eMMC.
"""
import argparse
import importlib.util
import os
import struct
import sys

here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("sc", os.path.join(here, "serial-console.py"))
sc = importlib.util.module_from_spec(spec)
sys.path.insert(0, here)
spec.loader.exec_module(sc)
LOADADDR = 0x01080000


def dtb_offset(path):
    h = open(path, "rb").read(1660)
    assert h[:8] == b"ANDROID!"
    ksz, _, rsz, _, ssz, _, _, page = struct.unpack("<8I", h[8:40])
    ver = struct.unpack("<I", h[40:44])[0]
    assert ver == 2, f"header v{ver}"
    rdo_size = struct.unpack("<I", h[1632:1636])[0]
    dtb_size = struct.unpack("<I", h[1648:1652])[0]
    pg = lambda n: (n + page - 1) // page * page
    return page + pg(ksz) + pg(rsz) + pg(ssz) + pg(rdo_size), dtb_size


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--bootimg", required=True)
    ap.add_argument("--set", action="append", default=[])
    ap.add_argument("--args", default="")
    ap.add_argument("--wait", type=float, default=1200)
    ap.add_argument("--after", type=float, default=240)
    a = ap.parse_args()
    off, size = dtb_offset(a.bootimg)
    dtb = LOADADDR + off
    print(f"dtb section at image offset 0x{off:x} ({size} bytes) -> RAM 0x{dtb:x}")
    c = sc.Console(a.port, os.path.join(here, "..", "out", f"serial-{a.port}.log"))
    print(f"{sc.now()} waiting up to {a.wait:.0f} s for a u-boot prompt - power-cycle the box now")
    if not c.break_in(a.wait):
        return 1
    out = c.send("", 1.0)
    if b"g12b_w400_v1#" in out and b"g12b_galilei_v1#" not in out:
        c.s.write(b"run preboot\n")
        if not c.break_in(60):
            return 1
    # raw read of the whole boot image (imgread kernel skips the v2 DTB section); the hook uses the
    # same syntax: store read <part> <addr> <offset> <size>
    c.send(f"store read boot 0x{LOADADDR:x} 0 0xc80000", 8.0)
    c.send(f"fdt addr 0x{dtb:x}", 1.0)
    c.send("fdt header", 1.5)
    for s in a.set:
        path, prop, val = s.split(" ", 2)
        c.send(f"fdt print {path} {prop}", 1.0)
        c.send(f"fdt set {path} {prop} {val}", 1.0)
        c.send(f"fdt print {path} {prop}", 1.0)
    c.send("run storeargs", 2.0)
    c.send("setenv bootargs ${bootargs} rootfstype=ramfs " + a.args, 1.0)
    c.s.write(f"bootm 0x{LOADADDR:x}\n".encode())
    c.pump(a.after)
    return 0


if __name__ == "__main__":
    sys.exit(main())
