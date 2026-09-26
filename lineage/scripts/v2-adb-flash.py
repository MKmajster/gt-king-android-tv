#!/usr/bin/env python3
"""Write partition images on the running v2 box over ADB (Wi-Fi, root), then reboot through our
u-boot prompt (UART) to (re)arm the boot watchdog in the env, and watch the boot.

    py -3.14 v2-adb-flash.py [--ip 192.168.0.100] [--image vendor=lineage/out/v2-m1j-vendor.img] [--no-flash]

Why: the v2 build is userdebug with adbd as root over Wi-Fi at ~55 MB/s, far faster and safer than
u-boot burn mode for big partitions (vendor 512 MiB). Steps:
  1. push each image to /data/local/tmp, compare sha256 with the local file;
  2. 'blockdev --setrw' (fs_mgr sets mounted read-only partitions RO: dd fails with EPERM), dd the
     image onto /dev/block/<part>, read it back and compare sha256 again (only the image length:
     the partition is bigger); the framework keeps running - 'stop' drops Wi-Fi and this adb link;
  3. 'reboot bootloader' -> our u-boot stops at its prompt for reboot reason 'bootloader';
  4. UART: prefix env 'storeboot' with the SoC watchdog arm (120 s) unless it is already there,
     saveenv (the USB Burning Tool resets the env to defaults, so this is needed after every package
     burn), 'reset';
  5. log the boot, wait for adb over Wi-Fi to come back, print boot_completed / Wi-Fi state.
"""
import argparse
import hashlib
import importlib.util
import os
import subprocess
import sys
import time

here = os.path.dirname(os.path.abspath(__file__))
top = os.path.abspath(os.path.join(here, "..", ".."))
spec = importlib.util.spec_from_file_location("sc", os.path.join(here, "serial-console.py"))
sc = importlib.util.module_from_spec(spec)
sys.path.insert(0, here)
spec.loader.exec_module(sc)
ADB = os.path.join(top, "tools", "platform-tools", "adb.exe")
WDT = "mw.l 0xffd0f0d0 0x0363a97f; mw.l 0xffd0f0d8 0x2ee0; mw.l 0xffd0f0dc 0; mw.l 0xffd0f0d0 0x0367a97f"


def adb(dev, *args, timeout=900, check=True):
    r = subprocess.run([ADB, "-s", dev, *args], capture_output=True, text=True, timeout=timeout,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise SystemExit(f"adb {' '.join(args)} failed: {r.stdout}{r.stderr}")
    return r.stdout.strip()


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", default=open(os.path.join(top, "lineage", "out", "box-ip.txt")).read().strip())
    ap.add_argument("--image", action="append", default=[], help="part=path")
    ap.add_argument("--no-flash", action="store_true", help="only the reboot + watchdog env step")
    ap.add_argument("--watch", type=float, default=150)
    ap.add_argument("--uart-reboot", action="store_true",
                    help="reboot via the Android serial console (setprop sys.powerctl) instead of adb")
    a = ap.parse_args()
    dev = f"{a.ip}:5555"
    subprocess.run([ADB, "connect", dev], capture_output=True)
    if not (a.no_flash and a.uart_reboot) and adb(dev, "shell", "id -u") != "0":
        adb(dev, "root", check=False); time.sleep(4); subprocess.run([ADB, "connect", dev], capture_output=True)
    for spec_ in ([] if a.no_flash else a.image):
        part, path = spec_.split("=", 1)
        size, want = os.path.getsize(path), sha256(path)
        remote = f"/data/local/tmp/{part}.img"
        print(f"{sc.now()} push {path} ({size >> 20} MiB) -> {remote}")
        adb(dev, "push", path, remote)
        got = adb(dev, "shell", f"sha256sum {remote}").split()[0]
        if got != want:
            raise SystemExit(f"sha256 mismatch after push: {got} vs {want}")
        blk = f"/dev/block/by-name/{part}"
        psize = int(adb(dev, "shell", f"blockdev --getsize64 {blk}"))
        if psize < size:
            raise SystemExit(f"{part}: image {size} > partition {psize}")
        # NOT 'stop': stopping the framework takes Wi-Fi (and this adb session) down mid-dd.
        # fs_mgr marks mounted read-only partitions' block devices RO (BLKROSET) -> 'setrw' first;
        # the reboot follows right after, so nothing runs long on the rewritten /vendor.
        print(f"{sc.now()} dd -> {blk}")
        adb(dev, "shell", f"blockdev --setrw $(readlink -f {blk}); dd if={remote} of={blk} bs=4M conv=fsync 2>&1 | tail -1; sync")
        back = adb(dev, "shell", f"head -c {size} {blk} | sha256sum").split()[0]
        print(f"{sc.now()} read back sha256 {back[:16]}.. {'OK' if back == want else 'MISMATCH'}")
        if back != want:
            raise SystemExit("partition read-back mismatch - NOT rebooting; fix before power loss")
        adb(dev, "shell", f"rm -f {remote}")
    c = sc.Console("COM9", os.path.join(top, "lineage", "out", "serial-COM9.log"))
    print(f"{sc.now()} reboot bootloader")
    if a.uart_reboot:
        c.s.write(b"\nsu 0 setprop sys.powerctl reboot,bootloader\n"); c.s.flush()
    else:
        subprocess.run([ADB, "-s", dev, "reboot", "bootloader"], capture_output=True, timeout=30)
    end = time.time() + 90
    while time.time() < end and not c.at_prompt():
        c.pump(1.0)
    if not c.at_prompt():
        c.break_in(60)
    out = c.send("printenv storeboot", 1.5)
    if b"0xffd0f0d0" not in out:
        c.send(f'setenv storeboot "{WDT}; ${{storeboot}}"', 1.0)
        c.send("saveenv", 3.0)
        print(f"\n{sc.now()} watchdog arm added to storeboot + saveenv")
    else:
        print(f"\n{sc.now()} storeboot already arms the watchdog")
    c.send("reset", 1.0)
    t = c.pump(a.watch)
    c.s.close()
    keys = [l for l in t.decode("utf-8", "replace").replace("\r", "\n").split("\n")
            if any(k in l for k in ("Starting application", "Find match dtb", "Starting kernel", "Kernel panic", "init second"))]
    print("\n".join(keys[:12]))
    for _ in range(40):
        subprocess.run([ADB, "connect", dev], capture_output=True)
        r = subprocess.run([ADB, "-s", dev, "shell", "getprop sys.boot_completed"], capture_output=True, text=True)
        if r.stdout.strip() == "1":
            break
        time.sleep(5)
    print(adb(dev, "shell", "getprop sys.boot_completed; getprop wlan.driver.status; cmd wifi status | head -1; "
                          "ip -4 -br addr show wlan0; uptime", check=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
