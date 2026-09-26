#!/usr/bin/env python3
"""Run commands in the Android serial console shell (userdebug 'console' service on ttyS0).

    py -3.14 uart-shell.py --port COM9 --cmd "getprop sys.boot_completed" [--cmd ...] [--wait 3]

Sends each command, collects the output for --wait seconds (kernel messages interleave), prints it,
and appends everything to lineage/out/serial-<port>.log. Retries opening a busy port for 30 s.
"""
import argparse, os, re, sys, time
import serial

ap = argparse.ArgumentParser()
ap.add_argument("--port", required=True); ap.add_argument("--cmd", action="append", default=[])
ap.add_argument("--wait", type=float, default=3.0)
a = ap.parse_args()
logpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out", f"serial-{a.port}.log")
log = open(logpath, "ab")
for i in range(30):
    try:
        s = serial.Serial(a.port, 115200, timeout=0.05); break
    except serial.SerialException:
        time.sleep(1)
else:
    raise SystemExit("port busy")

def pump(secs):
    end = time.time() + secs; got = b""
    while time.time() < end:
        d = s.read(65536)
        if d: got += d; log.write(d); log.flush()
    return got

s.write(b"\x03\n"); pump(0.8)   # fresh prompt
for c in a.cmd:
    s.write(c.encode() + b"\n"); s.flush()
    out = pump(a.wait)
    txt = re.sub(rb"[^\x20-\x7e\n]", b"", out).decode()
    # drop the kernel log lines that interleave on the console
    lines = [l for l in txt.splitlines() if l.strip() and not re.match(r"\[\s*\d+\.\d+@\d\]", l)]
    print(f"$ {c}"); print("\n".join(lines[-80:])); print()
s.close()
