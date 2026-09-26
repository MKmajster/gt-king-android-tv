#!/usr/bin/env python3
"""Run u-boot commands on the box in Amlogic USB burn mode and read env variables back through RAM.

  py -3.14 burn-cmd.py --cmd "imgread kernel boot 0x1080000" --vars "loadaddr avb2 system_mode" [--allenv] [--reset]

Each --cmd returns the burn-protocol status ("success" / "failed:..."); --vars exports the named
variables with 'env export -t' into scratch DDR and reads the text back (64-byte control reads).
Safe: nothing is written to eMMC. --reset sends the burn-protocol 'reset' (normal reboot) at the end.
"""
import argparse, os, sys, time

DLL = os.path.join(os.environ.get("APPDATA", ""), r"Python\Python314\site-packages\libusb\_platform\windows\x86_64")
if os.path.isdir(DLL):
    os.environ["PATH"] = DLL + os.pathsep + os.environ["PATH"]
    try:
        os.add_dll_directory(DLL)
    except Exception:
        pass
import usb.core  # noqa: E402
from pyamlboot import pyamlboot  # noqa: E402

VID, PID = 0x1B8E, 0xC003
SCRATCH = 0x0A000000


def log(m):
    print(time.strftime("%H:%M:%S") + " " + m, flush=True)


def cmd(dev, s, wait=0.4):
    dev.dev.ctrl_transfer(0x40, 0x30, 0, 1, s.encode("ascii") + b"\0", timeout=8000)
    time.sleep(wait)
    r = bytes(dev.dev.ctrl_transfer(0xC0, 0x31, 0, 0, 64, timeout=3000))
    return r.split(b"\0", 1)[0].decode("ascii", "replace")


def read(dev, addr, n):
    out = b""
    while len(out) < n:
        out += bytes(dev.readSimpleMemory(addr + len(out), min(64, n - len(out))))
    return out


def export(dev, what, n=1024):
    # clear the scratch area first so stale text from earlier exports cannot leak into the result
    cmd(dev, f"mw.b 0x{SCRATCH:x} 0 0x{n:x}", wait=0.3)
    r = cmd(dev, f"env export -t 0x{SCRATCH:x} {what}".strip(), wait=0.6)
    raw = read(dev, SCRATCH, n)
    txt = raw.split(b"\0\0", 1)[0].decode("ascii", "replace")
    return r, [ln for ln in txt.split("\0") if ln]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cmd", action="append", default=[])
    ap.add_argument("--vars", default="")
    ap.add_argument("--allenv", action="store_true")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--wait", type=float, default=2)
    a = ap.parse_args()
    if usb.core.find(idVendor=VID, idProduct=PID) is None:
        log("no burn-mode device present")
        return 2
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from amlusb import open_soc, describe
    dev, backend = open_soc()          # retrying IDENTIFY (works through WinUSB and libusb0.sys)
    b = dev.ident
    log(f"[{backend}] IDENTIFY {describe(b)}")
    for c in a.cmd:
        log(f"[{c}] -> {cmd(dev, c, wait=a.wait)}")
    if a.vars:
        r, lines = export(dev, a.vars)
        log(f"export({a.vars}) -> {r}")
        for ln in lines:
            print("   " + ln)
    if a.allenv:
        r, lines = export(dev, "", 8192)
        log(f"export(all) -> {r}: {len(lines)} vars")
        for ln in lines:
            print("   " + ln[:300])
    if a.reset:
        log("reset -> normal reboot")
        try:
            dev.dev.ctrl_transfer(0x40, 0x30, 0, 1, b"reset\0", timeout=3000)
        except Exception as e:
            log(f"(expected) {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
