#!/usr/bin/env python3
"""Send magic SysRq over the UART console (serial BREAK + key) and log the answer.
    py -3.14 uart-sysrq.py --port COM9 w l [t] [--secs 6]
w = blocked (D-state) tasks with stacks, l = backtrace of all active CPUs, t = all tasks,
m = memory, p = registers. Output is appended to lineage/out/serial-<port>.log and printed.
Useful when the kernel stops printing but is still alive (timers keep running).
"""
import argparse
import os
import sys
import time

import serial


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--secs", type=float, default=6)
    ap.add_argument("keys", nargs="+")
    a = ap.parse_args()
    here = os.path.dirname(os.path.abspath(__file__))
    log = open(os.path.join(here, "..", "out", f"serial-{a.port}.log"), "ab")
    s = serial.Serial(a.port, 115200, timeout=0.05)
    for k in a.keys:
        print(f"\n===== {time.strftime('%H:%M:%S')} SysRq {k}")
        s.send_break(duration=0.3)
        time.sleep(0.05)
        s.write(k.encode())
        end = time.time() + a.secs
        while time.time() < end:
            d = s.read(8192)
            if d:
                log.write(d); log.flush()
                sys.stdout.write(d.decode("utf-8", "replace")); sys.stdout.flush()
    s.close()


if __name__ == "__main__":
    main()
