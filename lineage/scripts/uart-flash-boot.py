#!/usr/bin/env python3
"""Write a boot.img (or any partition image) over the UART console at high speed, then boot it.
    py -3.14 uart-flash-boot.py --port COM9 --image boot.img [--part boot] [--baud 921600]
        [--no-boot] [--watchdog] [--wait 3600] [--after 240]
1. catch the galilei u-boot prompt (Ctrl-C; 'run preboot' if the stock one is caught first);
2. 'setenv baudrate <baud>' - u-boot switches its console and waits for ENTER at the new speed;
3. YMODEM 'loady' to 0x1080000 (uart-ymodem.py's sender), then 'crc32' of the RAM copy is compared
   with the file's CRC32 - nothing is written unless they match;
4. 'store write <part> 0x1080000 0 <size>'; back to 115200;
5. unless --no-boot: optionally arm the SoC watchdog (120 s, so a kernel that hangs before its own
   watchdog driver resets the box back to u-boot), then 'run storeargs; run storeboot'.
At 115200 a 12.8 MB boot.img takes ~25 min, at 921600 ~3-4 min. Log: lineage/out/serial-<port>.log.
"""
import argparse
import importlib.util
import os
import sys
import time
import zlib

here = os.path.dirname(os.path.abspath(__file__))


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(here, file))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


sys.path.insert(0, here)
sc = load("sc", "serial-console.py")
ym = load("ym", "uart-ymodem.py")
ADDR = 0x1080000
WDT = ["mw.l 0xffd0f0d0 0x0363a97f", "mw.l 0xffd0f0d8 0x2ee0", "mw.l 0xffd0f0dc 0", "mw.l 0xffd0f0d0 0x0367a97f"]


def switch_baud(c, baud):
    c.s.write(f"setenv baudrate {baud}\n".encode()); c.s.flush()
    c.pump(1.0)
    c.s.baudrate = baud
    time.sleep(0.3)
    c.s.write(b"\r"); c.s.flush()
    out = c.pump(1.5)
    c.s.write(b"\n"); out += c.pump(1.0)
    return b"g12b_galilei_v1#" in out


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--image", required=True)
    ap.add_argument("--part", default="boot")
    ap.add_argument("--baud", type=int, default=921600)
    ap.add_argument("--no-boot", action="store_true")
    ap.add_argument("--watchdog", action="store_true")
    ap.add_argument("--wait", type=float, default=3600)
    ap.add_argument("--after", type=float, default=240)
    a = ap.parse_args()
    data = open(a.image, "rb").read()
    crc = zlib.crc32(data) & 0xFFFFFFFF
    print(f"{a.image}: {len(data)} bytes, crc32 {crc:08x}")
    c = sc.Console(a.port, os.path.join(here, "..", "out", f"serial-{a.port}.log"))
    c.s.write(b"\n"); c.pump(1.0)
    if not c.at_prompt():
        print(f"{sc.now()} waiting up to {a.wait:.0f} s for a u-boot prompt - power-cycle the box if it hangs")
        if not c.break_in(a.wait):
            return 1
    out = c.send("", 1.0)
    if b"g12b_w400_v1#" in out and b"g12b_galilei_v1#" not in out:
        c.s.write(b"run preboot\n")
        if not c.break_in(60):
            return 1
    if a.baud != 115200 and not switch_baud(c, a.baud):
        print(f"no prompt at {a.baud}, back to 115200")
        c.s.baudrate = 115200
        c.s.write(b"\r\n"); c.pump(1.0)
        return 1
    snd = ym.Sender.__new__(ym.Sender)
    snd.s, snd.log = c.s, c.log
    snd.transfer(f"0x{ADDR:x}", a.image, data)
    out = c.send(f"crc32 0x{ADDR:x} 0x{len(data):x}", 3.0)
    if f"{crc:08x}".encode() not in out.lower():
        print(f"CRC MISMATCH (want {crc:08x}) - nothing written")
        switch_baud(c, 115200)
        return 1
    print(f"{sc.now()} crc32 ok, writing {a.part}")
    out = c.send(f"store write {a.part} 0x{ADDR:x} 0 0x{len(data):x}", 30.0)
    if a.baud != 115200:
        switch_baud(c, 115200)
        c.s.baudrate = 115200
    if a.no_boot:
        return 0
    if a.watchdog:
        for w in WDT:
            c.send(w, 0.3)
    c.send("run storeargs", 2.0)
    c.s.write(b"run storeboot\n"); c.s.flush()
    c.pump(a.after)
    return 0


if __name__ == "__main__":
    sys.exit(main())
