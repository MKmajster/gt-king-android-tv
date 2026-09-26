#!/usr/bin/env python3
"""u-boot serial console helper for the GT-King PRO (RS232 DB9 on the back = UART_AO, 115200 8N1).

    py -3.14 serial-console.py --port COM3 --watch 30            just log what the box prints
    py -3.14 serial-console.py --port COM3 --break                hammer Ctrl-C until a u-boot prompt appears
    py -3.14 serial-console.py --port COM3 --break --fix-hook     ...then install the chainload hook (hook.py) + saveenv
    py -3.14 serial-console.py --port COM3 --break --drop-hook    ...then delete 'preboot' (stock boots as before) + saveenv
    py -3.14 serial-console.py --port COM3 --break --cmd "printenv preboot" --cmd "run update"

Ctrl-C is not disabled during 'preboot' in this u-boot config (no CONFIG_AUTOBOOT_KEYED), so a stream of
Ctrl-C aborts the env hook loop; the autoboot countdown (bootdelay=1) is then interrupted too.
Everything printed by the box is appended to lineage/out/serial-<port>.log.
"""
import argparse, os, sys, time
import serial  # pyserial

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hook  # noqa: E402
HOOK_PARTS = hook.SETENV_CMDS  # the one hook definition (see hook.py)
PROMPTS = (b"g12b_galilei_v1#", b"g12b_w400_v1#", b"=> ", b"# ")


def now():
    return time.strftime("%H:%M:%S")


class Console:
    def __init__(self, port, logpath, baud=115200):
        self.s = serial.Serial(port, baud, timeout=0.05)
        self.log = open(logpath, "ab")
        self.buf = b""

    def pump(self, secs):
        """read for `secs` seconds; echo + log; return the bytes read."""
        end = time.time() + secs
        got = b""
        while time.time() < end:
            d = self.s.read(4096)
            if d:
                got += d
                self.log.write(d); self.log.flush()
                sys.stdout.write(d.decode("utf-8", "replace")); sys.stdout.flush()
        self.buf = (self.buf + got)[-8192:]
        return got

    def at_prompt(self):
        tail = self.buf[-200:]
        return any(p in tail for p in PROMPTS)

    def send(self, text, wait=1.0):
        self.s.write(text.encode("ascii") + b"\n"); self.s.flush()
        return self.pump(wait)

    def break_in(self, seconds=40):
        """Send Ctrl-C bursts until a u-boot prompt shows up."""
        print(f"{now()} sending Ctrl-C bursts for up to {seconds}s ...")
        end = time.time() + seconds
        while time.time() < end:
            self.s.write(b"\x03" * 4); self.s.flush()
            self.pump(0.15)
            if self.at_prompt():
                # settle: one more newline and check the prompt again
                self.s.write(b"\n"); self.pump(0.4)
                if self.at_prompt():
                    print(f"\n{now()} *** u-boot prompt ***")
                    return True
        print(f"\n{now()} no prompt")
        return False


def main():
    # the box prints binary garbage at times (power glitches, baud changes): never let stdout encoding kill us
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", required=True)
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--watch", type=float, default=0, help="seconds to just log output")
    ap.add_argument("--break", dest="brk", action="store_true")
    ap.add_argument("--break-seconds", type=float, default=40)
    ap.add_argument("--fix-hook", action="store_true")
    ap.add_argument("--drop-hook", action="store_true")
    ap.add_argument("--cmd", action="append", default=[])
    ap.add_argument("--after", type=float, default=0, help="seconds to keep logging after the last command (e.g. --cmd reset --after 180)")
    a = ap.parse_args()
    logpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out", f"serial-{a.port}.log")
    c = Console(a.port, logpath, a.baud)
    print(f"{now()} open {a.port} {a.baud} 8N1, log -> {logpath}")
    if a.watch:
        c.pump(a.watch)
    if a.brk:
        if not c.break_in(a.break_seconds):
            return 2
        c.send("echo console-ok", 0.5)
        c.send("printenv aml_dt preboot upgrade_step reboot_mode", 1.0)
    if a.fix_hook or a.drop_hook:
        if a.drop_hook:
            c.send("setenv preboot", 0.5)
        else:
            for p in HOOK_PARTS:
                c.send(p, 0.4)
        c.send("setenv upgrade_step 2", 0.4)
        c.send("saveenv", 2.5)
        c.send("printenv preboot", 1.0)
    for cmd in a.cmd:
        c.send(cmd, 1.5)
    if a.after:
        c.pump(a.after)
    if a.brk or a.fix_hook or a.drop_hook or a.cmd:
        print(f"\n{now()} done (box is sitting at the u-boot prompt; 'reset' to reboot, 'update' for USB burn mode)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
