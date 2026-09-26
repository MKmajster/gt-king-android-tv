#!/usr/bin/env python3
"""Decisive RAM test of the galilei u-boot BL33 through the stock u-boot's USB burn mode.

Sequence (box must already be in burn mode: Android -> cable in USB 2.0 port -> adb reboot update):
  1. IDENTIFY, set a RAM-only env marker in the running (stock) u-boot, export env to RAM, read it back
  2. upload our BL33 to 0x01000000 (caches off), 'go' there
  3. re-attach, IDENTIFY again, export env again and read it back:
       marker still there  -> the stock u-boot is still running (jump failed)
       marker gone         -> a NEW u-boot instance re-imported env from eMMC = OUR u-boot is running
  4. if ours: optionally 'run storeboot' so it boots the stock Android kernel (USB detaches on bootm)

Windows: py -3.14 chainload-test.py [--bl33 PATH] [--storeboot] [--wait SEC]
Nothing is written to eMMC (the marker lives in RAM only; env is never saved).
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
EXPORT_ADDR = 0x0A000000   # scratch DDR for 'env export -t'
LOAD_ADDR = 0x01000000     # BL33 link/entry address


def now():
    return time.strftime("%H:%M:%S") + ".%03d" % int((time.time() % 1) * 1000)


def log(m):
    print(f"{now()} {m}", flush=True)


def find(timeout):
    t = time.time() + timeout
    while time.time() < t:
        try:
            if usb.core.find(idVendor=VID, idProduct=PID) is not None:
                return True
        except Exception:
            pass
        time.sleep(0.1)
    return False


def identify(dev):
    b = bytes(dev.dev.ctrl_transfer(0xC0, 0x20, 0, 0, 8, timeout=3000))
    return f"ROM {b[0]}.{b[1]} Stage {b[2]}.{b[3]} pw={b[4]}/{b[5]}"


def cmd(dev, s, wait=0.4):
    dev.dev.ctrl_transfer(0x40, 0x30, 0, 1, s.encode("ascii") + b"\0", timeout=5000)
    time.sleep(wait)
    r = bytes(dev.dev.ctrl_transfer(0xC0, 0x31, 0, 0, 64, timeout=3000))
    return r.split(b"\0", 1)[0].decode("ascii", "replace")


def read(dev, addr, n):
    out = b""
    while len(out) < n:
        chunk = min(64, n - len(out))
        out += bytes(dev.readSimpleMemory(addr + len(out), chunk))
    return out


def export_env(dev, what=""):
    r = cmd(dev, f"env export -t 0x{EXPORT_ADDR:x} {what}".strip(), wait=0.6)
    raw = read(dev, EXPORT_ADDR, 256)
    txt = raw.split(b"\0\0", 1)[0].decode("ascii", "replace").replace("\0", " | ")
    return r, txt


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bl33", default=os.path.join(os.path.dirname(__file__), "..", "out", "u-boot-galilei-bl33-raw.bin"))
    ap.add_argument("--wait", type=float, default=30)
    ap.add_argument("--storeboot", action="store_true", help="if our u-boot is running, tell it to 'run storeboot'")
    a = ap.parse_args()

    if not find(a.wait):
        log("no burn-mode device")
        return 2
    dev = pyamlboot.AmlogicSoC()
    log("stage 1: " + identify(dev))
    log("probe: " + cmd(dev, "echo hi"))
    log("marker: " + cmd(dev, "setenv aaa_marker stock_uboot_ram_only"))
    r, txt = export_env(dev, "aaa_marker ver")
    log(f"export(ver,marker) -> {r}: {txt}")
    if "aaa_marker" not in txt:
        r, txt = export_env(dev)
        log(f"export(all) -> {r}: {txt[:200]}")

    data = open(a.bl33, "rb").read()
    data += b"\0" * (-len(data) % 4096)
    log("dcache off -> " + cmd(dev, "dcache off"))
    log(f"upload {len(data)} bytes -> 0x{LOAD_ADDR:08x}")
    dev.writeLargeMemory(LOAD_ADDR, data, 4096)
    head = read(dev, LOAD_ADDR, 64)
    log("verify " + ("OK" if head == data[:64] else "MISMATCH"))
    if head != data[:64]:
        return 3
    log("icache off -> " + cmd(dev, "icache off"))
    log(f"go 0x{LOAD_ADDR:x}")
    try:
        dev.dev.ctrl_transfer(0x40, 0x30, 0, 1, f"go 0x{LOAD_ADDR:x}".encode() + b"\0", timeout=5000)
    except Exception as e:
        log(f"go send: {e}")

    # stage 2: whoever answers now
    time.sleep(6)
    gone_at = None
    for i in range(40):
        try:
            present = usb.core.find(idVendor=VID, idProduct=PID) is not None
        except Exception:
            present = False
        if present:
            break
        gone_at = gone_at or now()
        time.sleep(0.5)
    else:
        log(f"device did not come back after go (gone since {gone_at}) - our u-boot ran and left burn mode, or crashed")
        return 5
    try:
        dev = pyamlboot.AmlogicSoC()
        log("stage 2: " + identify(dev))
        r, txt = export_env(dev, "aaa_marker ver")
        log(f"export(ver,marker) -> {r}: {txt}")
        if "aaa_marker" in txt:
            log("RESULT: marker survived -> STOCK u-boot still running, the jump did not take over")
            return 1
        log("RESULT: marker gone -> env re-imported from eMMC -> OUR u-boot (galilei BL33) IS RUNNING")
        r, txt = export_env(dev)
        log(f"env head: {txt[:200]}")
        if a.storeboot:
            log("run storeboot (USB will detach on bootm; Android should boot under our u-boot)")
            try:
                dev.dev.ctrl_transfer(0x40, 0x30, 0, 1, b"run storeboot\0", timeout=5000)
            except Exception as e:
                log(f"(expected) {e}")
        return 0
    except Exception as e:
        log(f"stage 2 failed: {e}")
        return 6


if __name__ == "__main__":
    sys.exit(main())
