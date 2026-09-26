#!/usr/bin/env python3
"""Install / remove the chainload hook in the STOCK u-boot environment of the GT-King (see hook.py).

The stock bootloader (BL2/BL30/BL31/BL33 from Beelink) stays untouched. Its env variable
'preboot' (which overrides the compiled-in CONFIG_PREBOOT) is set to:

    run upgrade_check; forceupdate; if store read bl33 0x1000000 0 0x140000; then dcache off; icache off; go 0x1000000; fi; run update

NOTE: the stock env is reset by 'defenv_reserv' on the first boot after a USB burn (upgrade_step=1) and
'preboot' is not in the reserved list (aml_dt, firstboot, lock, upgrade_step, bootloader_version) -
so run --set only AFTER the first boot following the flash, from the stock burn mode (pinhole at power-on).

  - 'forceupdate' first: the ADC pinhole key held ~4 s at power-on enters the stock USB burn mode
    before anything of ours runs (escape hatch: from there '--restore' undoes everything).
  - 'store read ... bl33' failing (no 'bl33' partition, stock layout) ends in 'run update' = a USB
    burn window, so install the hook only together with / after the chainload package.
  - our u-boot then handles reboot reasons itself (normal/recovery/update), reads the LineageOS
    partition table from the new _aml_dtb and boots boot.img.

Box must be in Amlogic USB burn mode (Android -> cable in USB 2.0 -> adb reboot update).
    py -3.14 chainload-env.py --show        print the current 'preboot' (via env export to RAM)
    py -3.14 chainload-env.py --set         setenv preboot ... ; saveenv   (writes the env partition!)
    py -3.14 chainload-env.py --restore     setenv preboot (delete) ; saveenv -> compiled default again
Backup of the untouched env partition: backup/20260914-stock/env.img (restorable with adb dd).
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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hook  # noqa: E402

VID, PID = 0x1B8E, 0xC003
SCRATCH = 0x0A000000
# Amlogic u-boot 2015 syntax: store read <partition> <addr> <offset> <size>
HOOK = hook.HOOK


def log(m):
    print(time.strftime("%H:%M:%S") + " " + m, flush=True)


def cmd(dev, s, wait=0.5):
    dev.dev.ctrl_transfer(0x40, 0x30, 0, 1, s.encode("ascii") + b"\0", timeout=8000)
    time.sleep(wait)
    r = bytes(dev.dev.ctrl_transfer(0xC0, 0x31, 0, 0, 64, timeout=3000))
    return r.split(b"\0", 1)[0].decode("ascii", "replace")


def read(dev, addr, n):
    out = b""
    while len(out) < n:
        out += bytes(dev.readSimpleMemory(addr + len(out), min(64, n - len(out))))
    return out


def get_var(dev, name):
    cmd(dev, f"mw.b 0x{SCRATCH:x} 0 0x400", wait=0.3)
    cmd(dev, f"env export -t 0x{SCRATCH:x} {name}", wait=0.6)
    raw = read(dev, SCRATCH, 1024)
    txt = raw.split(b"\0\0", 1)[0].decode("ascii", "replace")
    for ln in txt.split("\0"):
        if ln.startswith(name + "="):
            return ln[len(name) + 1:]
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--show", action="store_true")
    g.add_argument("--set", action="store_true")
    g.add_argument("--restore", action="store_true")
    a = ap.parse_args()
    if usb.core.find(idVendor=VID, idProduct=PID) is None:
        log("no burn-mode device (VID 1B8E PID C003) present")
        return 2
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from amlusb import open_soc, describe
    dev, backend = open_soc()          # retrying IDENTIFY (works through WinUSB and libusb0.sys)
    b = dev.ident
    log(f"[{backend}] IDENTIFY {describe(b)}")
    if b[3] != 16:
        log("not u-boot burn mode - refusing")
        return 3
    aml_dt = get_var(dev, "aml_dt")
    log(f"running u-boot selected DTB: aml_dt={aml_dt}")
    if aml_dt and "galilei" in aml_dt:
        log("this is OUR u-boot (chainloaded) - the hook must be edited from the STOCK u-boot; refusing")
        return 4
    cur = get_var(dev, "preboot")
    log(f"current preboot = {cur!r}")
    if a.show:
        return 0
    if a.set:
        for c in hook.SETENV_CMDS:  # < 64 bytes each (EP0 TPL_CMD limit)
            log(f"{c} -> {cmd(dev, c)}")
    else:
        log(f"setenv preboot (delete) -> {cmd(dev, 'setenv preboot')}")
    log(f"saveenv -> {cmd(dev, 'saveenv', wait=1.5)}")
    log(f"preboot now = {get_var(dev, 'preboot')!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
