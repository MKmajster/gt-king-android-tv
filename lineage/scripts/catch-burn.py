#!/usr/bin/env python3
"""Catch the stock u-boot's short USB burn window (box boot-looping: ~13 s in 'update' burn mode
per cycle) and, inside that window, install the chainload hook in the stock environment:

    setenv preboot "<hook.HOOK: run upgrade_check; forceupdate; if store read bl33 ...; then ... go 0x1000000; fi; run update>"
    setenv upgrade_step 2 ; saveenv ; [store write bl33] ; reset

IDENTIFY as the very first request clears u-boot's burn timeout, so once caught the box waits.
    py -3.14 catch-burn.py [--wait 120] [--show-only] [--restore]
"""
import argparse, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import amlusb  # noqa: E402
import hook  # noqa: E402
amlusb._prep_dlls()
import usb.core, usb.backend.libusb1 as lb1  # noqa: E402
from pyamlboot import pyamlboot  # noqa: E402

VID, PID = 0x1B8E, 0xC003
HOOK = hook.HOOK


def now():
    return time.strftime("%H:%M:%S") + ".%03d" % int((time.time() % 1) * 1000)


def log(m):
    print(f"{now()} {m}", flush=True)


def cmd(dev, s, wait=0.4, tries=3):
    last = None
    for _ in range(tries):
        try:
            dev.ctrl_transfer(0x40, 0x30, 0, 1, s.encode("ascii") + b"\0", timeout=5000)
            time.sleep(wait)
            r = bytes(dev.ctrl_transfer(0xC0, 0x31, 0, 0, 64, timeout=3000))
            return r.split(b"\0", 1)[0].decode("ascii", "replace")
        except Exception as e:
            last = e
            time.sleep(0.2)
    raise RuntimeError(f"cmd {s!r} failed: {last}")


def read_var(dev, name):
    """env export <name> into scratch DDR and read it back with 64-byte control reads."""
    cmd(dev, "mw.b 0x0a000000 0 0x400", wait=0.3)
    cmd(dev, f"env export -t 0x0a000000 {name}", wait=0.6)
    out = b""
    while len(out) < 256:
        chunk = None
        for _ in range(4):
            try:
                chunk = bytes(dev.ctrl_transfer(0xC0, 0x02, 0x0a00, len(out), 64, timeout=3000))
                if len(chunk) == 64:
                    break
            except Exception:
                time.sleep(0.2)
        if not chunk:
            break
        out += chunk
    txt = out.split(b"\0\0", 1)[0].decode("ascii", "replace")
    for ln in txt.split("\0"):
        if ln.startswith(name + "="):
            return ln[len(name) + 1:]
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wait", type=float, default=120)
    ap.add_argument("--show-only", action="store_true", help="only identify and print, do not change env")
    ap.add_argument("--restore", action="store_true", help="delete the hook instead of setting it")
    ap.add_argument("--cmd", action="append", default=[], help="run this u-boot command (<64 bytes) after catching; repeatable; no env change")
    ap.add_argument("--bl33", help="also write this padded BL33 image (lineage/out/bl33-v2.img) into the bl33 partition before reset")
    a = ap.parse_args()

    be = lb1.get_backend()
    deadline = time.time() + a.wait
    log(f"polling for {VID:04x}:{PID:04x} u-boot burn window (up to {a.wait:.0f}s) ...")
    attempts = 0
    while time.time() < deadline:
        try:
            dev = usb.core.find(idVendor=VID, idProduct=PID, backend=be)
        except Exception:
            dev = None
        if dev is None:
            time.sleep(0.15)
            continue
        attempts += 1
        try:
            b = bytes(dev.ctrl_transfer(0xC0, 0x20, 0, 0, 8, timeout=1500))
        except Exception as e:
            time.sleep(0.15)
            continue
        if len(b) < 8:
            time.sleep(0.15)
            continue
        log(f"caught: {amlusb.describe(b)} (after {attempts} attempts)")
        if b[3] != 16:
            log("not u-boot burn mode (Stage x.16) - keep polling")
            time.sleep(0.5)
            continue
        # we are in u-boot burn mode and the timeout is cleared by the IDENTIFY above
        log("probe: " + cmd(dev, "echo galilei"))
        try:
            log(f"aml_dt={read_var(dev, 'aml_dt')!r}  (only set for a MULTI dtb in _aml_dtb: stock g12b_w400_b; None with our single dtb)")
        except Exception as e:
            log(f"(aml_dt read failed: {e})")
        if a.cmd:
            for c in a.cmd:
                assert len(c) + 1 <= 64, c
                log(f"[{c}] -> " + cmd(dev, c, wait=0.6))
            return 0
        if a.show_only:
            return 0
        if a.restore:
            log("setenv preboot (delete) -> " + cmd(dev, "setenv preboot"))
        else:
            # TPL_CMD goes through EP0 (64-byte packets): every command must stay < 64 bytes,
            # so build the hook from short pieces and join them with hush expansion (hook.py).
            for p in hook.SETENV_CMDS:
                log(f"{p} -> " + cmd(dev, p))
        log("setenv upgrade_step 2 -> " + cmd(dev, "setenv upgrade_step 2"))
        log("saveenv -> " + cmd(dev, "saveenv", wait=1.5))
        if a.bl33:
            data = open(a.bl33, "rb").read()
            assert len(data) % 4096 == 0 and len(data) <= 0x200000, "bl33 image must be 4 KiB padded and <= 2 MiB"
            soc = pyamlboot.AmlogicSoC.__new__(pyamlboot.AmlogicSoC); soc.dev = dev
            log(f"upload bl33 ({len(data)} bytes) -> 0x01000000")
            cmd(dev, "dcache off", wait=0.3)
            soc.writeLargeMemory(0x01000000, data, 4096)
            head = b""
            try:
                head = bytes(dev.ctrl_transfer(0xC0, 0x02, 0x0100, 0x0000, 64, timeout=3000))
            except Exception:
                pass
            log("upload head verify: " + ("OK" if head == data[:64] else f"unverified ({len(head)} bytes read back)"))
            if head and head != data[:64]:
                log("upload MISMATCH - not writing bl33"); return 3
            log(f"store write bl33 -> " + cmd(dev, f"store write bl33 0x1000000 0 0x{len(data):x}", wait=2.0))
        # verify by printing into the burn status buffer is not possible; re-read via env export to RAM
        try:
            cmd(dev, "mw.b 0x0a000000 0 0x400", wait=0.3)
            cmd(dev, "env export -t 0x0a000000 preboot", wait=0.6)
            out = b""
            while len(out) < 256:
                out += bytes(dev.ctrl_transfer(0xC0, 0x02, 0x0a00, len(out), 64, timeout=3000))
            txt = out.split(b"\0\0", 1)[0].decode("ascii", "replace").replace("\0", " | ")
            log("env now: " + txt[:200])
        except Exception as e:
            log(f"(verify read skipped: {e})")
        log("reset -> normal reboot")
        try:
            dev.ctrl_transfer(0x40, 0x30, 0, 1, b"reset\0", timeout=3000)
        except Exception as e:
            log(f"(expected) {e}")
        return 0
    log("no burn window caught")
    return 2


if __name__ == "__main__":
    sys.exit(main())
