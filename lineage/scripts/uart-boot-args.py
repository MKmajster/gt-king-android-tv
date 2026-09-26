#!/usr/bin/env python3
"""Boot the box once with extra kernel arguments, from the galilei u-boot prompt over UART (no flash).
    py -3.14 uart-boot-args.py --port COM9 --args "initcall_debug" [--wait 900] [--after 180]
Hammers Ctrl-C until a u-boot prompt appears (power-cycle the box meanwhile). If the STOCK u-boot
(g12b_w400_v1#) is caught first, 'run preboot' runs the chain-load hook and the galilei u-boot
(g12b_galilei_v1#) is caught next - booting from the stock prompt would skip our BL33 (A73 clock setup).
Then: setenv initargs ${initargs} <args>; run storeargs; run storeboot. Nothing is saved (no saveenv).
Output is appended to lineage/out/serial-<port>.log as with serial-console.py.
"""
import argparse
import importlib.util
import os
import sys
import time

here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("sc", os.path.join(here, "serial-console.py"))
sc = importlib.util.module_from_spec(spec)
sys.path.insert(0, here)
spec.loader.exec_module(sc)


def main():
    # UART noise is not cp1250-encodable (the Windows console default): never die on it
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--args", required=True)
    ap.add_argument("--wait", type=float, default=900)
    ap.add_argument("--after", type=float, default=180)
    a = ap.parse_args()
    logpath = os.path.join(here, "..", "out", f"serial-{a.port}.log")
    c = sc.Console(a.port, logpath)
    print(f"{sc.now()} waiting up to {a.wait:.0f} s for a u-boot prompt - power-cycle the box now")
    if not c.break_in(a.wait):
        print("no prompt"); return 1
    out = c.send("", 1.0)
    if b"g12b_w400_v1#" in out and b"g12b_galilei_v1#" not in out:
        print(f"{sc.now()} stock u-boot prompt -> run preboot (chain-load), then break into galilei")
        c.s.write(b"run preboot\n")
        if not c.break_in(60):
            print("no galilei prompt"); return 1
        out = c.send("", 1.0)
        if b"g12b_galilei_v1#" not in out:
            print("still not at the galilei prompt:", out[-200:]); return 1
    # storeboot uses the ${bootargs} that storeargs built earlier in the boot: rebuild them after the change
    c.send("setenv initargs ${initargs} " + a.args, 1.0)
    c.send("run storeargs", 2.0)
    c.send("printenv bootargs", 1.5)
    c.s.write(b"run storeboot\n")
    c.pump(a.after)
    return 0


if __name__ == "__main__":
    sys.exit(main())
