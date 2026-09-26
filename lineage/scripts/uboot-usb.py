#!/usr/bin/env python3
"""Talk to the GT-King PRO over USB in Amlogic "update" (u-boot burn) mode or BootROM mode.

Windows: py -3.14 uboot-usb.py [--wait SEC] [--cmd "u-boot command"]... [--dumpenv] [--go BL33.bin [--addr 0x1000000]]
                                [--bootrom u-boot.bin]

Flow: wait for USB VID 1B8E PID C003 (needs the WinUSB driver, see ramboot-win.ps1), send IDENTIFY at once
(u-boot clears its burn-mode timeout on IDENTIFY, so the box then stays in burn mode indefinitely),
print ROM/stage (stage minor 16 = u-boot "TPL", 0 = BootROM), then:
  --cmd    run u-boot commands through TPL_CMD (result = success/failed via TPL_STAT; command output goes to the serial console)
  --dumpenv  'env export -t' into RAM and read it back over USB (shows the live u-boot environment)
  --go     upload a raw BL33 (u-boot.bin from build/, entry 0x01000000) into DDR and jump to it ("chainload"):
           tests our u-boot on the real board without touching eMMC. The USB link drops when the new u-boot starts.
  --bootrom  BootROM only: classic boot-g12 flow (BL2 into SRAM + AMLC upload of the rest).
Nothing here writes to eMMC by itself; power-cycling the box always returns to the stock bootloader.
"""
import argparse, os, sys, time, struct

DLL = os.path.join(os.environ.get("APPDATA", ""), r"Python\Python314\site-packages\libusb\_platform\windows\x86_64")
if os.path.isdir(DLL):
    os.environ["PATH"] = DLL + os.pathsep + os.environ["PATH"]
    try:
        os.add_dll_directory(DLL)
    except Exception:
        pass

import usb.core  # noqa: E402
from pyamlboot import pyamlboot  # noqa: E402

REQ_TPL_STAT = 0x31
VID, PID = 0x1B8E, 0xC003
WAIT_FRESH = [True]


def now():
    return time.strftime("%H:%M:%S") + ".%03d" % int((time.time() % 1) * 1000)


def log(msg):
    print(f"{now()} {msg}", flush=True)


def wait_device(timeout):
    deadline = time.time() + timeout
    # a device that is already present may be a wedged session from before: wait for a fresh arrival,
    # unless --now says to use whatever is present right now (box already sitting in burn mode)
    try:
        if usb.core.find(idVendor=VID, idProduct=PID) is not None:
            if not WAIT_FRESH[0]:
                return True
            log("device already present - waiting for it to go away first (power-cycle the box)")
            while time.time() < deadline and usb.core.find(idVendor=VID, idProduct=PID) is not None:
                time.sleep(0.2)
    except usb.core.NoBackendError:
        log("libusb backend missing (libusb-1.0.dll not found)")
        return False
    log(f"waiting up to {deadline - time.time():.0f}s for USB {VID:04x}:{PID:04x} ...")
    while time.time() < deadline:
        try:
            if usb.core.find(idVendor=VID, idProduct=PID) is not None:
                return True
        except usb.core.NoBackendError:
            log("libusb backend missing (libusb-1.0.dll not found)")
            return False
        except Exception as e:  # transient enumeration errors
            log(f"find: {e}")
        time.sleep(0.05)
    return False


def tpl_stat(dev, length=64):
    # EP0 max packet is 64 bytes: never ask for more (a 512-byte read wedged the u-boot burn loop on 2026-09-15)
    ret = dev.dev.ctrl_transfer(bmRequestType=0xC0, bRequest=REQ_TPL_STAT, wValue=0, wIndex=0,
                                data_or_wLength=min(length, 64), timeout=3000)
    return bytes(ret).split(b"\0", 1)[0].decode("ascii", "replace")


def tpl_cmd(dev, cmd, wait=0.3):
    dev.dev.ctrl_transfer(bmRequestType=0x40, bRequest=0x30, wValue=0, wIndex=1,
                          data_or_wLength=cmd.encode("ascii") + b"\0", timeout=5000)
    time.sleep(wait)
    return tpl_stat(dev)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wait", type=float, default=600)
    ap.add_argument("--now", action="store_true", help="use a device already present (do not wait for a fresh arrival)")
    ap.add_argument("--cmd", action="append", default=[], help="u-boot command to run (repeatable)")
    ap.add_argument("--dumpenv", action="store_true")
    ap.add_argument("--go", help="raw BL33 image to chainload")
    ap.add_argument("--addr", type=lambda x: int(x, 0), default=0x01000000)
    ap.add_argument("--bootrom", help="packed u-boot.bin for BootROM mode (boot-g12 flow)")
    ap.add_argument("--bootm", help="u-boot legacy image (mkimage -T standalone) to upload and start with 'bootm' (burn mode detaches USB first)")
    ap.add_argument("--loadaddr", type=lambda x: int(x, 0), default=0x08000000, help="where to upload the --bootm image")
    ap.add_argument("--keep", action="store_true", help="stay connected (poll) after the actions instead of exiting")
    a = ap.parse_args()
    WAIT_FRESH[0] = not a.now

    if not wait_device(a.wait):
        log("no device")
        return 2
    t0 = time.time()
    try:
        dev = pyamlboot.AmlogicSoC()
    except Exception as e:
        log(f"open failed: {e}")
        return 3
    try:
        ident = dev.identify()
    except Exception as e:
        log(f"IDENTIFY failed: {e} (device wedged? power-cycle the box)")
        return 4
    b = [ord(c) for c in ident]
    stage = "u-boot(TPL)" if len(b) > 3 and b[3] == 16 else ("BootROM" if len(b) > 3 and b[3] == 0 else f"unknown({b[3] if len(b)>3 else '?'})")
    log(f"IDENTIFY in {time.time()-t0:.2f}s: ROM {b[0]}.{b[1]} Stage {b[2]}.{b[3]} -> {stage}; pw needed={b[4] if len(b)>4 else '?'} ok={b[5] if len(b)>5 else '?'}")

    if stage == "BootROM":
        if not a.bootrom:
            log("BootROM mode but no --bootrom image given; nothing to do")
            return 0
        data = open(a.bootrom, "rb").read()
        log(f"BootROM: writing BL2 (64 KiB of {a.bootrom}) to 0xfffa0000")
        dev.writeLargeMemory(0xFFFA0000, data[0:0x10000], 4096)
        dev.run(0xFFFA0000)
        time.sleep(2)
        prev = (-1, -1)
        seq = 0
        while True:
            length, offset = dev.getBootAMLC()
            if (length, offset) == prev:
                log("[BL2 END]")
                break
            prev = (length, offset)
            log(f"AMLC dataSize={length} offset={offset} seq={seq}")
            dev.writeAMLCData(seq, offset, data[offset:offset + length])
            seq += 1
        return 0

    # u-boot burn mode
    log("probe: " + tpl_cmd(dev, "echo galilei-usb-alive"))
    for c in a.cmd:
        r = tpl_cmd(dev, c, wait=0.5)
        log(f"cmd [{c}] -> {r}")
    if a.dumpenv:
        tmp = 0x08000000
        r = tpl_cmd(dev, f"env export -t 0x{tmp:x}", wait=0.5)
        log(f"env export -> {r}")
        raw = bytes(dev.readLargeMemory(tmp, 16384, 4096))
        txt = raw.split(b"\0\0", 1)[0].decode("ascii", "replace")
        lines = [ln for ln in txt.split("\0") if ln.strip()]
        log(f"env: {len(lines)} vars")
        for ln in lines:
            print("   " + ln)
    if a.go:
        data = open(a.go, "rb").read()
        data += b"\0" * (-len(data) % 4096)   # bulk transfer wants whole blocks
        # stock u-boot ran from this address before relocating: drop stale cache lines first
        log("dcache off -> " + tpl_cmd(dev, "dcache off"))
        log(f"chainload: uploading {len(data)} bytes to 0x{a.addr:08x} ...")
        t1 = time.time()
        dev.writeLargeMemory(a.addr, data, 4096)
        log(f"upload done in {time.time()-t1:.1f}s; verifying head and tail")
        ok = True
        try:
            head = bytes(dev.readSimpleMemory(a.addr, 64))
            tail = bytes(dev.readSimpleMemory(a.addr + len(data) - 64, 64))
            ok = head == data[:64] and tail == data[-64:]
            log("verify " + ("OK" if ok else "MISMATCH head=" + head.hex()[:32] + " tail=" + tail.hex()[:32]))
        except Exception as e:
            log(f"verify read failed ({e}); proceeding anyway (write path is reliable)")
        if ok:
            log("icache off -> " + tpl_cmd(dev, "icache off"))
            log(f"go 0x{a.addr:x}  (USB link will drop; watch HDMI)")
            try:
                dev.tplCommand(1, f"go 0x{a.addr:x}".encode("ascii") + b"\0")
            except Exception as e:
                log(f"(expected) link dropped: {e}")
        else:
            log("dcache on -> " + tpl_cmd(dev, "dcache on"))
    if a.bootm:
        data = open(a.bootm, "rb").read()
        data += b"\0" * (-len(data) % 4096)
        log("dcache off -> " + tpl_cmd(dev, "dcache off"))
        log(f"bootm: uploading {len(data)} bytes to 0x{a.loadaddr:08x} ...")
        dev.writeLargeMemory(a.loadaddr, data, 4096)
        try:
            head = bytes(dev.readSimpleMemory(a.loadaddr, 64))
            log("verify " + ("OK" if head == data[:64] else "MISMATCH " + head.hex()[:32]))
        except Exception as e:
            log(f"verify read failed ({e}); proceeding")
        log("iminfo -> " + tpl_cmd(dev, f"iminfo 0x{a.loadaddr:x}", wait=0.5))
        log(f"bootm 0x{a.loadaddr:x}  (burn mode detaches USB, then jumps; watch HDMI)")
        try:
            dev.dev.ctrl_transfer(bmRequestType=0x40, bRequest=0x30, wValue=0, wIndex=1,
                                  data_or_wLength=f"bootm 0x{a.loadaddr:x}".encode("ascii") + b"\0", timeout=5000)
            time.sleep(0.5)
            log("post-bootm stat: " + tpl_stat(dev))
        except Exception as e:
            log(f"(expected if the image took over) link dropped: {e}")
    if a.keep:
        log("keeping the session (Ctrl-C to stop)")
        while usb.core.find(idVendor=VID, idProduct=PID) is not None:
            time.sleep(1)
        log("device gone")
    return 0


if __name__ == "__main__":
    sys.exit(main())
