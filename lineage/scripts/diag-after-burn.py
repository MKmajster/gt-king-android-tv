#!/usr/bin/env python3
"""Hardware diagnostics from the u-boot USB burn window, without UART.

Waits for a NEW "Burning successfully" in today's USB Burning Tool log, closes the tool (it would grab
the box again), catches the u-boot burn session that the box is still sitting in, and runs:
  1. env: upgrade_step / reboot_mode / aml_dt (which u-boot, what state)
  2. eMMC read speed: timed 'store read' of boot (16 MiB) and system (64 MiB) -> MB/s (retries/CRC
     errors on damaged CLK/CMD lines show up as a crawl; the kernel at HS200 then fails outright)
  3. DDR: u-boot 'mtest' over 0x10000000..0xE0000000 in 256 MiB chunks (the kernel uses all 4 GB,
     u-boot only tens of MB - a bad row is invisible to u-boot but kills every kernel)
Every command runs synchronously inside u-boot's USB loop, so TPL_STAT is polled with retries until
u-boot answers again (long commands simply time out the control transfers meanwhile).

    py -3.14 lineage/scripts/diag-after-burn.py [--no-wait-log] [--skip-mtest] [--reset]
"""
import argparse, glob, os, re, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import amlusb  # noqa: E402
amlusb._prep_dlls()
import usb.core, usb.backend.libusb1 as lb1  # noqa: E402

VID, PID = 0x1B8E, 0xC003
LOGDIR = r"C:\Program Files (x86)\Amlogic\USB_Burning_Tool\log"


def log(m):
    print(time.strftime("%H:%M:%S") + " " + m, flush=True)


def tool_log_count():
    d = os.path.join(LOGDIR, time.strftime("%Y.%m"), time.strftime("%Y.%m.%d"))
    n = 0
    for f in glob.glob(os.path.join(d, "*.txt")):
        try:
            n += open(f, "rb").read().count(b"Burning successfully")
        except Exception:
            pass
    return n


def tpl_stat(dev):
    return bytes(dev.ctrl_transfer(0xC0, 0x31, 0, 0, 64, timeout=3000)).split(b"\0", 1)[0].decode("ascii", "replace")


def cmd_long(dev, s, deadline_s=600):
    """Send a u-boot command and poll its status until u-boot is back in the USB loop."""
    assert len(s) + 1 <= 64, s
    dev.ctrl_transfer(0x40, 0x30, 0, 1, s.encode("ascii") + b"\0", timeout=5000)
    t0 = time.time()
    time.sleep(0.3)
    last = None
    while time.time() - t0 < deadline_s:
        try:
            st = tpl_stat(dev)
            return st, time.time() - t0
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
            return ln[len(name) + 1:]
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-wait-log", action="store_true", help="do not wait for a new Burning successfully; catch whatever u-boot burn window appears")
    ap.add_argument("--skip-mtest", action="store_true")
    ap.add_argument("--mtest-end", type=lambda s: int(s, 0), default=0xE0000000)
    ap.add_argument("--wait", type=float, default=1800)
    ap.add_argument("--reset", action="store_true", help="u-boot reset at the end")
    a = ap.parse_args()

    if not a.no_wait_log:
        base = tool_log_count()
        log(f"armed: waiting for a new 'Burning successfully' (baseline {base}) - flash the package now")
        while tool_log_count() <= base:
            time.sleep(1)
        log("Burning successfully seen -> closing USB_Burning_Tool")
        subprocess.run(["taskkill", "/IM", "USB_Burning_Tool.exe", "/F"], capture_output=True)
        time.sleep(2)

    be = lb1.get_backend()
    deadline = time.time() + a.wait
    log("polling for the u-boot burn window ...")
    dev = None
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
            break
        dev = None
        time.sleep(0.5)
    if dev is None:
        log("no u-boot burn window"); return 2

    st, dt = cmd_long(dev, "echo diag", 10)
    log(f"probe: {st}")
    for v in ("upgrade_step", "reboot_mode", "aml_dt", "bootloader_version"):
        log(f"env {v} = {read_var(dev, v)!r}")

    log("eMMC: mmcinfo -> " + cmd_long(dev, "mmcinfo", 30)[0])
    for part, size in (("boot", 0x1000000), ("system", 0x4000000), ("vendor", 0x4000000)):
        st, dt = cmd_long(dev, f"store read {part} 0x10000000 0 0x{size:x}", 600)
        log(f"eMMC: store read {part} {size >> 20} MiB -> {st} in {dt:.1f}s = {size / dt / 1e6:.1f} MB/s")
    # second pass on boot: retries/CRC errors are erratic, a healthy eMMC is consistent
    st, dt = cmd_long(dev, "store read boot 0x10000000 0 0x1000000", 600)
    log(f"eMMC: store read boot again -> {st} in {dt:.1f}s = {0x1000000 / dt / 1e6:.1f} MB/s")

    if not a.skip_mtest:
        start = 0x10000000
        step = 0x10000000
        while start < a.mtest_end:
            end = min(start + step, a.mtest_end)
            st, dt = cmd_long(dev, f"mtest 0x{start:x} 0x{end:x} 0 1", 900)
            log(f"DDR: mtest 0x{start:08x}-0x{end:08x} -> {st} in {dt:.0f}s")
            if "success" not in st:
                log("DDR: FAILURE in this range (or u-boot did not come back) - stopping the memory test")
                break
            start = end
    if a.reset:
        try:
            dev.ctrl_transfer(0x40, 0x30, 0, 1, b"reset\0", timeout=5000)
        except Exception:
            pass
    log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
