#!/usr/bin/env python3
"""Run boot experiments on the box unattended, over the UART console, without flashing anything.
    py -3.14 uart-experiments.py --port COM9 --bootimg <local copy of the flashed boot.img>
        --exp "nosdio: /sdio@ffe03000 status okax" --exp "nosd: /sd@ffe05000 status okax" ...
        [--args "initcall_debug ignore_loglevel"] [--first-wait 3600]
For every experiment: catch the galilei u-boot prompt (Ctrl-C; 'run preboot' when the stock prompt is
caught first), arm the SoC watchdog for 120 s (mw.l on WATCHDOG_CNTL/TCNT at 0xffd0f0d0, what u-boot's
watchdog_init() does), load boot.img to RAM, apply the in-RAM DTB edits (same-length values: the blob
has no free space), rebuild bootargs and bootm. A kernel that hangs before its own watchdog driver
takes over is reset after 120 s, which brings the next u-boot prompt - so only the very first prompt
needs a manual power-cycle. Result per experiment: reached init ("Freeing unused kernel memory") or
not, plus the last initcall that never returned. Stops at the first experiment that reaches init.
Log: lineage/out/serial-<port>.log; summary: lineage/out/uart-experiments.txt.
"""
import argparse
import importlib.util
import os
import re
import sys
import time

here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("sc", os.path.join(here, "serial-console.py"))
sc = importlib.util.module_from_spec(spec)
sys.path.insert(0, here)
spec.loader.exec_module(sc)
spec2 = importlib.util.spec_from_file_location("dp", os.path.join(here, "uart-boot-dtpatch.py"))
dp = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(dp)

LOADADDR = 0x01080000
# 120 s: divider 240000 (10 ms ticks, bits 0-17), TCNT 12000; bits 24/25/22/21 as in watchdog_init(), 18 = enable
WDT = ["mw.l 0xffd0f0d0 0x0363a97f", "mw.l 0xffd0f0d8 0x2ee0", "mw.l 0xffd0f0dc 0", "mw.l 0xffd0f0d0 0x0367a97f"]


def catch_prompt(c, secs):
    if not c.break_in(secs):
        return False
    out = c.send("", 1.0)
    if b"g12b_w400_v1#" in out and b"g12b_galilei_v1#" not in out:
        c.s.write(b"run preboot\n")
        return c.break_in(60)
    return True


def watch_boot(c, secs):
    """Collect kernel output until init is reached or the output stops; return the text."""
    text = b""
    end = time.time() + secs
    quiet_since = time.time()
    while time.time() < end:
        d = c.pump(1.0)
        if d:
            text += d
            quiet_since = time.time()
            if b"Freeing unused kernel memory" in text:
                return text + c.pump(20), True     # plus some init output for the record
        elif time.time() - quiet_since > 45 and b"Starting kernel" in text:
            return text, False    # silent for 45 s: hung; the 120 s watchdog resets the SoC later
        k = text.rfind(b"Starting kernel")
        if k >= 0 and b"G12B:BL" in text[k:]:
            return text, False    # it already reset (new BL2 banner): go catch the prompt now
    return text, b"Freeing unused kernel memory" in text


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--bootimg", required=True)
    ap.add_argument("--exp", action="append", required=True, help='"name: /path prop value; /path prop value"')
    ap.add_argument("--args", default="")
    ap.add_argument("--first-wait", type=float, default=3600)
    a = ap.parse_args()
    off, _ = dp.dtb_offset(a.bootimg)
    dtb = LOADADDR + off
    c = sc.Console(a.port, os.path.join(here, "..", "out", f"serial-{a.port}.log"))
    summary = open(os.path.join(here, "..", "out", "uart-experiments.txt"), "a", encoding="utf-8")
    first = True
    for e in a.exp:
        name, _, edits = e.partition(":")
        name = name.strip()
        print(f"\n##### {sc.now()} experiment {name}: {edits.strip()}")
        if not catch_prompt(c, a.first_wait if first else 300):
            summary.write(f"{sc.now()} {name}: no u-boot prompt (power-cycle needed)\n"); summary.flush()
            return 1
        first = False
        for w in WDT:
            c.send(w, 0.3)
        # raw read of the whole boot image (imgread kernel skips the v2 DTB section); the hook uses the
        # same syntax: store read <part> <addr> <offset> <size>
        c.send(f"store read boot 0x{LOADADDR:x} 0 0xc80000", 8.0)
        c.send("fdt header", 1.5)
        c.send(f"fdt addr 0x{dtb:x}", 1.0)
        for ed in [x.strip() for x in edits.split(";") if x.strip()]:
            if ed.startswith("rm "):          # delete a node: frees room inside the blob for longer values
                c.send(f"fdt {ed}", 1.0)
                continue
            path, prop, val = ed.split(" ", 2)
            c.send(f"fdt set {path} {prop} {val}", 1.0)
            c.send(f"fdt print {path} {prop}", 1.0)
        c.send("run storeargs", 2.0)
        c.send("setenv bootargs ${bootargs} rootfstype=ramfs " + a.args, 1.0)
        c.s.write(f"bootm 0x{LOADADDR:x}\n".encode())
        text, ok = watch_boot(c, 400)
        t = text.decode("utf-8", "replace")
        calls = re.findall(r"calling\s+(\S+)", t)
        rets = set(re.findall(r"initcall (\S+) returned", t))
        pending = [x for x in calls if x not in rets]
        line = f"{sc.now()} {name}: {'REACHED INIT' if ok else 'hung'}; pending initcalls {pending[-3:]}"
        print("\n" + line)
        summary.write(line + "\n"); summary.flush()
        if ok:
            c.pump(120)
            return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
