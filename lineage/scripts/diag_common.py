"""Shared helpers for the USB burn-window diagnostics (diag-after-burn.py, diag2-after-burn.py)."""
import time
import usb.core, usb.backend.libusb1 as lb1
import amlusb

VID, PID = 0x1B8E, 0xC003


def log(m):
    print(time.strftime("%H:%M:%S") + " " + m, flush=True)


def tpl_stat(dev):
    return bytes(dev.ctrl_transfer(0xC0, 0x31, 0, 0, 64, timeout=3000)).split(b"\0", 1)[0].decode("ascii", "replace")


def cmd_long(dev, s, deadline_s=600):
    """Send a u-boot command (TPL_CMD, < 64 bytes) and poll TPL_STAT until u-boot is back in its USB loop."""
    assert len(s) + 1 <= 64, s
    dev.ctrl_transfer(0x40, 0x30, 0, 1, s.encode("ascii") + b"\0", timeout=5000)
    t0 = time.time()
    time.sleep(0.3)
    last = None
    while time.time() - t0 < deadline_s:
        try:
            return tpl_stat(dev), time.time() - t0
        except Exception as e:
            last = e
            time.sleep(1.0)
    return f"no status after {deadline_s}s ({last})", time.time() - t0


def read_var(dev, name):
    cmd_long(dev, "mw.b 0x0a000000 0 0x400", 10)
    cmd_long(dev, f"env export -t 0x0a000000 {name}", 10)
    out = b""
    while len(out) < 256:
        try:
            out += bytes(dev.ctrl_transfer(0xC0, 0x02, 0x0a00, len(out), 64, timeout=3000))
        except Exception:
            break
    for ln in out.split(b"\0\0", 1)[0].decode("ascii", "replace").split("\0"):
        if ln.startswith(name + "="):
            return ln[len(name) + 1:].rstrip("\n")
    return None


def catch_uboot(wait_s):
    """Poll for the 1B8E:C003 u-boot burn window; IDENTIFY as the first request clears its timeout."""
    be = lb1.get_backend()
    deadline = time.time() + wait_s
    log("polling for the u-boot burn window ...")
    while time.time() < deadline:
        try:
            dev = usb.core.find(idVendor=VID, idProduct=PID, backend=be)
        except Exception:
            dev = None
        if dev is None:
            time.sleep(0.15); continue
        try:
            b = bytes(dev.ctrl_transfer(0xC0, 0x20, 0, 0, 8, timeout=1500))
        except Exception:
            time.sleep(0.15); continue
        if len(b) >= 8 and b[3] == 16:
            log(f"caught: {amlusb.describe(b)}")
            return dev
        time.sleep(0.5)
    return None
