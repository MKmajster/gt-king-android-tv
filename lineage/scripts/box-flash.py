#!/usr/bin/env python3
"""Unattended flash cycle for the v2 work - no USB Burning Tool, no hands on the box.
    py -3.14 box-flash.py [--image boot=img] [--image vendor=img] [--image _aml_dtb=img] [--watch 150]
1. reach the galilei u-boot prompt over UART:
   - already there -> fine;
   - Android serial console shell (userdebug) -> 'setprop sys.powerctl reboot,bootloader' (SELinux is
     permissive) and our u-boot stops at its prompt for reboot reason 'bootloader';
   - anything else (booting, hung) -> Ctrl-C bursts for up to --catch seconds; a kernel that hangs
     before its watchdog driver is reset by the watchdog that storeboot arms (env, 2026-09-26);
2. arm the SoC watchdog (120 s) and enter burn mode ('update'): a wedged USB session resets itself;
   usb-flash-part.py reloads the watchdog between pieces;
3. write every --image over USB (CRC-checked), the last one with 'reset';
4. log the boot for --watch seconds (lineage/out/box-flash-<time>.txt) and print the key lines.
Exit codes: 0 ok, 1 no prompt, 2 a USB write failed.
"""
import argparse
import importlib.util
import os
import re
import subprocess
import sys
import time

here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("sc", os.path.join(here, "serial-console.py"))
sc = importlib.util.module_from_spec(spec)
sys.path.insert(0, here)
spec.loader.exec_module(sc)
PORT = "COM9"
WDT = ["mw.l 0xffd0f0d0 0x0363a97f", "mw.l 0xffd0f0d8 0x2ee0", "mw.l 0xffd0f0dc 0", "mw.l 0xffd0f0d0 0x0367a97f"]
KEYS = re.compile(r"Freeing unused|init second stage|InitFatalReboot|Abort message|surfaceflinger|"
                  r"boot_completed|Boot is finished|bootanim|wlan0|dhd|mali0|Kernel panic|Restarting", re.I)


def open_console():
    for _ in range(40):
        try:
            return sc.Console(PORT, os.path.join(here, "..", "out", f"serial-{PORT}.log"))
        except Exception:
            time.sleep(1)
    raise SystemExit("COM9 busy")


def reach_prompt(c, catch):
    c.s.write(b"\n"); out = c.pump(1.5)
    if b"g12b_galilei_v1#" in out:
        return True
    if b"console:/" in out or out.rstrip().endswith(b"$"):
        print(f"{sc.now()} Android shell -> reboot,bootloader")
        c.s.write(b"setprop sys.powerctl reboot,bootloader\n"); c.pump(2.0)
    if not c.break_in(catch):
        return False
    out = c.send("", 1.0)
    if b"g12b_w400_v1#" in out and b"g12b_galilei_v1#" not in out:
        c.s.write(b"run preboot\n")
        return c.break_in(60)
    return True


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", action="append", default=[], help="part=path, in write order")
    ap.add_argument("--catch", type=float, default=400)
    ap.add_argument("--watch", type=float, default=150)
    a = ap.parse_args()
    c = open_console()
    if not reach_prompt(c, a.catch):
        print("no u-boot prompt"); return 1
    if a.image:
        for w in WDT:
            c.send(w, 0.3)
        c.send("update", 3.0)
        c.s.close()
        for i, spec_ in enumerate(a.image):
            part, path = spec_.split("=", 1)
            args = [sys.executable, "-u", os.path.join(here, "usb-flash-part.py"), "--image", path, "--part", part, "--wait", "60"]
            if part in ("_aml_dtb", "dtb"):
                args += ["--addr", "0x1000000"]
            if i < len(a.image) - 1:
                args.append("--no-reset")
            r = subprocess.run(args)
            if r.returncode != 0:
                print(f"USB write of {part} failed ({r.returncode}); the armed watchdog resets the box")
                return 2
        c = open_console()
    else:
        c.send("reset", 1.0)
    stamp = time.strftime("%H%M%S")
    t = c.pump(a.watch)
    out = os.path.join(here, "..", "out", f"box-flash-{stamp}.txt")
    open(out, "wb").write(t)
    lines = t.decode("utf-8", "replace").replace("\r", "\n").split("\n")
    print("\n".join(l[:200] for l in lines if KEYS.search(l))[:6000])
    print(f"log: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
