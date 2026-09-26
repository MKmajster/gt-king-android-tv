#!/usr/bin/env python3
"""ESP32-C3 (native USB-Serial-JTAG, MicroPython) as a 3.3 V USB<->UART bridge for the GT-King PRO
u-boot console (UART_AO, 115200 8N1), with a pad prober, a LED contact monitor and a
corruption-tolerant way to drive u-boot over a marginal wire.

Wiring (ESP32-C3 SuperMini; pad numbers as in lineage/out/uart_pads_zoom.png, 1 = square pad):
    box GND (pad 4 / screw ring)  -> G           always first
    box TX  (pad 2)               -> GPIO2       (ESP RX)   --rx 2
    box RX  (pad 3)               -> GPIO3       (ESP TX)   --tx 3
    box 3V3 (pad 1)               -> NOTHING

Why the received text is garbage even when the wire works: a poor through-hole contact is a series
resistance, and the ESP-IDF UART driver enables a pull-up on RX, so the box's LOW level never gets
below V_IL. Every corrupted bit is therefore a 0 that arrived as a 1 ('timeout' -> 'wimeouv'),
which is why this script (a) disables that pull-up, (b) matches text by bit-superset with a limit on
added bits, and (c) detects the u-boot prompt by the STREAM GOING SILENT under Ctrl-C, not by text.

    py -3.14 esp32-bridge.py --probe                 classify the pads on GPIO2/3/4 (inputs only, safe)
    py -3.14 esp32-bridge.py --contact 120           LED blinks while pad-2 contact is real
    py -3.14 esp32-bridge.py --auto 45               wait for contact -> break -> fix hook -> saveenv -> reset
    py -3.14 esp32-bridge.py --watch 20              raw view
    py -3.14 esp32-bridge.py --break --fix-hook
    py -3.14 esp32-bridge.py --break --cmd "printenv preboot" --cmd "update"
    py -3.14 esp32-bridge.py --decode lineage/out/serial-COM4.log    what u-boot strings are in a capture
    py -3.14 esp32-bridge.py --loopback              self-test with a jumper GPIO2<->GPIO3

Everything the box prints is appended to lineage/out/serial-<port>.log.
"""
import argparse, os, sys, time
import serial, serial.tools.list_ports

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ESC = b"\x1d\x1d\x1d"   # 3x Ctrl-] : leave the bridge / monitor loop

BRIDGE = r'''
import sys, micropython, select
from machine import UART, Pin
micropython.kbd_intr(-1)
u = UART(1, baudrate=%d, tx=%d, rx=%d, rxbuf=4096, txbuf=2048, timeout=0)
Pin(%d, Pin.IN, pull=%s)          # undo the pull-up that uart_set_pin() puts on RX
led = Pin(8, Pin.OUT); led.value(1)
p = select.poll(); p.register(sys.stdin, select.POLLIN)
esc = 0
sys.stdout.write("\r\n<<BRIDGE-READY>>\r\n")
while True:
    n = u.any()
    if n:
        sys.stdout.write(u.read(n))
        led.value(not led.value())    # blinks while the box's TX really reaches us
    if p.poll(1):
        c = sys.stdin.read(1)
        if c == "\x1d":
            esc += 1
            if esc >= 3:
                break
            continue
        esc = 0
        if c:
            u.write(c)
micropython.kbd_intr(3)
u.deinit()
sys.stdout.write("\r\n<<BRIDGE-EXIT>>\r\n")
'''

PROBE = r'''
import time, os
from machine import ADC, Pin, time_pulse_us
def adc_run(a, ms):
    lo = 99999; hi = 0; tot = 0; cnt = 0; low = 0
    t = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), t) < ms:
        v = a.read_uv() // 1000
        if v < lo: lo = v
        if v > hi: hi = v
        if v < 800: low += 1
        tot += v; cnt += 1
    return (lo, hi, tot // cnt, cnt, low)
def pulse_run(pin, ms):
    h = {}
    n = 0; t = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), t) < ms:
        w = time_pulse_us(pin, 0, 2000)
        time.sleep_us(50)
        if w > 0:
            n += 1
            b = 2 if w < 4 else (9 if w < 13 else (17 if w < 22 else (26 if w < 31 else (35 if w < 40 else (50 if w < 90 else (104 if w < 130 else 999))))))
            h[b] = h.get(b, 0) + 1
    return (n, sorted(h.items()))
print("FILES", os.listdir())
for n in PINS:
    try:
        p = Pin(n, Pin.IN, pull=None)
        a = ADC(Pin(n), atten=ADC.ATTN_11DB)
        r1 = adc_run(a, %d)
        Pin(n, Pin.IN, Pin.PULL_DOWN); time.sleep_ms(20)
        r2 = adc_run(a, 250)
        Pin(n, Pin.IN, Pin.PULL_UP); time.sleep_ms(20)
        r3 = adc_run(a, 250)
        p = Pin(n, Pin.IN, pull=None); time.sleep_ms(10)
        r4 = pulse_run(p, 1500)
        print("PROBE", n, repr((r1, r2, r3, r4)))
    except Exception as e:
        print("PROBE", n, repr(("ERR", str(e))))
print("<<PROBE-DONE>>")
'''

# Contact monitor: bit-wide low pulses on the RX wire = the box TX really reaches the ESP32.
# LED (GPIO8 on the SuperMini) BLINKS while the contact is good, stays on otherwise.
MONITOR = r'''
import sys, time, select
from machine import Pin, ADC, time_pulse_us
led = Pin(8, Pin.OUT); led.value(1)
rx = Pin(%d, Pin.IN, pull=None)
Pin(%d, Pin.IN, Pin.PULL_DOWN)
atx = ADC(Pin(%d), atten=ADC.ATTN_11DB)
p = select.poll(); p.register(sys.stdin, select.POLLIN)
sys.stdout.write("\r\n<<MON-READY>>\r\n")
run = True
while run:
    good = 0; spikes = 0; n = 0; t = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), t) < 400:
        w = time_pulse_us(rx, 0, 2000)
        if w > 0:
            n += 1
            if 6 <= w <= 45: good += 1
            elif w < 4: spikes += 1
        time.sleep_us(50)          # feed the interrupt watchdog: tight time_pulse_us loops panic
        if p.poll(0):
            if sys.stdin.read(1) == "\x1d":
                run = False
                break
    v = atx.read_uv() // 1000
    if good >= 30:
        led.value(not led.value())
    else:
        led.value(1)
    sys.stdout.write("MON %%d %%d %%d %%d\r\n" %% (good, spikes, n, v))
led.value(1)
sys.stdout.write("\r\n<<MON-EXIT>>\r\n")
'''

# Purely digital continuity test. Reading the pad through the ADC is unreliable, because putting a
# pin into analog mode drops the internal pull resistors; Pin.value() with each pull is definitive:
#   pull-down 0 and pull-up 1  -> nothing on the wire (floating)
#   1 with both pulls          -> wire sits on something driven/pulled HIGH (an idle TX, an RX with
#                                 its pull-up, or 3V3)
#   0 with both pulls          -> wire sits on GND
PINTEST = r'''
import time
from machine import Pin
for n in PINS:
    try:
        d = Pin(n, Pin.IN, Pin.PULL_DOWN); time.sleep_ms(40)
        lo = sum(d.value() for _ in range(64))
        u = Pin(n, Pin.IN, Pin.PULL_UP); time.sleep_ms(40)
        hi = sum(u.value() for _ in range(64))
        Pin(n, Pin.IN, pull=None)
        print("PIN", n, lo, hi)
    except Exception as e:
        print("PIN", n, -1, -1)
print("<<PINTEST-DONE>>")
'''

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hook  # noqa: E402
HOOK_PARTS = hook.SETENV_CMDS  # the one hook definition (see hook.py)
MARKERS = ["U-Boot 20", "g12b_w400_v1#", "g12b_s922x_galilei", "Net:   dwmac", "MMC:   aml_priv->desc_buf",
           "Saving Environment", "store read", "upgrade_key", "Loading Environment", "bootloader_version"]


def popcount(x):
    return bin(x).count("1")


def tol_find(buf, needle, max_added_per_char=1.6):
    """Positions where `buf` could be `needle` corrupted by 0->1 bit flips only.
    Returns (count, best_added_bits). A run of 0xFF matches every needle, so the number of
    ADDED bits per character is what separates a real match from noise."""
    n = needle.encode() if isinstance(needle, str) else needle
    L = len(n)
    if L == 0 or len(buf) < L:
        return 0, None
    limit = max_added_per_char * L
    hits = 0; best = None
    for i in range(len(buf) - L + 1):
        added = 0
        for j in range(L):
            b = buf[i + j]
            if (b & n[j]) != n[j]:
                added = -1; break
            added += popcount(b & ~n[j])
            if added > limit:
                added = -1; break
        if added >= 0:
            hits += 1
            if best is None or added < best:
                best = added
    return hits, best


def now():
    return time.strftime("%H:%M:%S")


ESPRESSIF = 0x303A
# Plain USB-TTL adapters that need no bridge firmware at all.
USB_TTL_VIDS = {
    0x0403: "FTDI",           # FT232R/FT2232 (also inside VAG-KKL cables)
    0x1A86: "CH340/CH341",
    0x10C4: "Silicon Labs CP210x",
    0x067B: "Prolific PL2303",
    0x2341: "Arduino",
    0x2A03: "Arduino",
    0x2E8A: "Raspberry Pi (Pico)",
    0x1B4F: "SparkFun",
}


def list_adapters():
    """Every serial port that could drive the box, newest style first."""
    out = []
    for p in serial.tools.list_ports.comports():
        if p.vid == ESPRESSIF:
            out.append((p.device, "bridge", "ESP32 (MicroPython bridge)"))
        elif p.vid in USB_TTL_VIDS:
            out.append((p.device, "direct", USB_TTL_VIDS[p.vid]))
        elif p.vid:
            out.append((p.device, "direct", f"USB {p.vid:04X}:{p.pid:04X}"))
    return out


def detect_port(prefer=None):
    ads = list_adapters()
    if prefer:
        for dev, mode, _ in ads:
            if dev.upper() == prefer.upper():
                return dev
    for dev, mode, _ in ads:      # a plain USB-TTL adapter is the simpler, more reliable path
        if mode == "direct":
            return dev
    return ads[0][0] if ads else None


class Link:
    """Either an ESP32 running the MicroPython bridge, or a plain USB-TTL adapter wired straight to
    the box ("direct"). In direct mode there is no firmware in the middle: the serial port IS the
    box's console, so the bridge/probe machinery is skipped and everything else works unchanged."""

    def __init__(self, port, logpath, mode="bridge", baud=115200):
        s = serial.Serial()
        s.port = port; s.baudrate = baud; s.timeout = 0.05; s.write_timeout = 1.5
        # Keep both handshake lines low: they reset the ESP32-C3 (USB-JTAG) and equally reset an
        # Arduino used as an adapter.
        s.dtr = False; s.rts = False
        s.open()
        self.s = s
        self.mode = mode
        self.log = open(logpath, "ab")
        self.buf = b""
        self.bridging = (mode == "direct")      # in direct mode everything received is box output

    # ---- raw serial helpers -------------------------------------------------
    def wr(self, data, chunk=48):
        """Chunked, retrying write: the C3's USB-CDC OUT endpoint is small and blocks when the
        firmware is busy, which raises SerialTimeoutException on Windows."""
        for i in range(0, len(data), chunk):
            part = data[i:i + chunk]
            for attempt in range(2):
                try:
                    self.s.write(part)
                    break
                except serial.SerialTimeoutException:
                    self.raw(0.15)
                except Exception as e:
                    print(f"{now()} serial write error ({e}) - reopening")
                    self.bridging = False
                    self.reopen()
                    raise RuntimeError("serial link reset")
            else:
                raise RuntimeError("serial write blocked")
            if len(data) > chunk:
                self.raw(0.01)

    def raw(self, secs):
        end = time.time() + secs; got = b""
        while time.time() < end:
            try:
                d = self.s.read(4096)
            except Exception as e:
                # the C3 re-enumerates on any USB hiccup; recover instead of dying
                print(f"{now()} serial read error ({e}) - reopening")
                self.bridging = False
                if not self.reopen():
                    time.sleep(1.0)
                return got
            if d:
                got += d
                if self.bridging:
                    self.log.write(d); self.log.flush()
        return got

    def pump(self, secs):
        got = self.raw(secs)
        if got:
            sys.stdout.write(got.decode("utf-8", "replace")); sys.stdout.flush()
        self.buf = (self.buf + got)[-65536:]
        return got

    def reopen(self, wait=12):
        """The C3's USB-Serial-JTAG is inside the chip: a reset re-enumerates the device and the
        old COM handle dies, so close and wait for the port to come back."""
        try:
            self.s.close()
        except Exception:
            pass
        end = time.time() + wait
        while time.time() < end:
            time.sleep(0.4)
            if any(p.device == self.s.port for p in serial.tools.list_ports.comports()):
                try:
                    self.s.open()
                    self.s.dtr = False; self.s.rts = False
                    time.sleep(0.3)
                    return True
                except Exception:
                    pass
        return False

    def hw_reset(self):
        """USB-Serial-JTAG reset: RTS high with DTR low pulls EN low, then the chip re-enumerates,
        so the port must be closed and reopened (esptool's USBJTAGSerialReset does the same)."""
        if self.mode == "direct":
            self.reopen()
            return b""
        print(f"{now()} hardware reset of the ESP32-C3")
        try:
            self.s.setRTS(True); self.s.setDTR(False); time.sleep(0.2)
            self.s.setRTS(False); time.sleep(0.2)
            self.s.close()
        except Exception:
            pass
        time.sleep(1.5)
        self.reopen()
        return self.raw(1.0)

    def to_repl(self):
        """Leave a running bridge/monitor, interrupt anything else, land in the normal REPL.
        A stale bridge on the ESP32 can stop draining the USB OUT endpoint, which blocks our
        writes; the only way out of that is the hardware reset."""
        self.bridging = False
        for attempt in range(4):
            try:
                self.wr(ESC); out = self.raw(0.5)
                self.wr(b"\x03\x03\x02"); out += self.raw(0.6)
                if b">>>" in out:
                    return True
            except Exception as e:
                print(f"{now()} REPL attempt {attempt + 1}: {e}")
            if attempt < 3:
                self.hw_reset()
                try:
                    self.wr(b"\x03\x02")
                    if b">>>" in self.raw(0.8):
                        return True
                except Exception:
                    pass
        return False

    def exec_raw(self, code, marker, timeout):
        if self.mode == "direct":
            raise RuntimeError("adapter USB-TTL nie ma pokładowej diagnostyki (to tryb bez pośrednika)")
        if not self.to_repl():
            raise RuntimeError("no MicroPython REPL on this port")
        self.wr(b"\x01"); out = self.raw(0.5)
        if b"raw REPL" not in out:
            raise RuntimeError(f"raw REPL not entered: {out[-100:]!r}")
        self.wr(code.encode("ascii")); self.wr(b"\x04")
        got = b""; end = time.time() + timeout
        while time.time() < end:
            got += self.raw(0.1)
            if marker in got:
                break
        return got

    # ---- bridge --------------------------------------------------------------
    def start_bridge(self, baud, tx, rx, rx_pull):
        if self.mode == "direct":
            if self.s.baudrate != baud:
                self.s.baudrate = baud
            self.bridging = True
            print(f"{now()} adapter USB-TTL na {self.s.port}, {baud} 8N1 - bez pośrednika")
            return True
        pull = {"none": "None", "up": "Pin.PULL_UP", "down": "Pin.PULL_DOWN"}[rx_pull]
        out = self.exec_raw(BRIDGE % (baud, tx, rx, rx, pull), b"<<BRIDGE-READY>>", 5)
        ok = b"<<BRIDGE-READY>>" in out
        self.bridging = ok
        print(f"{now()} bridge: " + ("READY (UART1 %d, rx=GPIO%d pull=%s, tx=GPIO%d)" % (baud, rx, rx_pull, tx)
                                     if ok else "FAILED " + repr(out[-160:])))
        return ok

    def stop_bridge(self):
        if self.mode == "direct":
            return
        if self.bridging:
            self.wr(ESC); self.raw(0.6); self.bridging = False
            self.wr(b"\x02"); self.raw(0.2)

    def send(self, text, wait=1.0):
        self.wr(text.encode("ascii") + b"\n")
        return self.pump(wait)

    # ---- prompt detection on a corrupted link --------------------------------
    def verify_prompt(self):
        """The received text cannot be trusted, so prove the prompt by making u-boot ECHO:
        a silent link answers nothing, a prompt answers our command plus its output."""
        self.raw(0.3)
        self.wr(b"\r\n"); a = self.raw(0.5)
        self.wr(b"echo AAAAAAAA\r\n"); b = self.raw(0.8)
        hits, added = tol_find(b, "AAAAAAAA", 1.2)
        ok = len(b) >= 12 and (hits > 0 or len(b) >= 24)
        print(f"{now()} prompt test: newline -> {len(a)} B, 'echo AAAAAAAA' -> {len(b)} B, "
              f"tolerant 'AAAAAAAA' hits={hits} (best +{added} bits) => {'PROMPT' if ok else 'no'}")
        return ok

    def break_in(self, seconds=40, listen=1.2):
        """Alternate a Ctrl-C storm with a listening pause. At the u-boot prompt Ctrl-C only
        re-prints the prompt, so the corruption-proof signal is: the box was talking (contact
        exists), and during a pause with nothing sent it stays SILENT. Confirm with the echo test.
        Silence while nothing was ever received just means the wire lost contact."""
        print(f"{now()} Ctrl-C storm for up to {seconds:.0f}s (hammer 0.8s / listen {listen}s) ...")
        end = time.time() + seconds
        total = 0; recent = []; last = 0; tries = 0
        while time.time() < end:
            hammer_end = time.time() + 0.8
            hammered = 0
            while time.time() < hammer_end:
                self.wr(b"\x03" * 8)
                n = len(self.raw(0.1)); hammered += n
            got = len(self.raw(listen))          # pause: send nothing, just listen
            total += hammered + got
            recent = [(t, v) for t, v in recent if time.time() - t < 12] + [(time.time(), hammered + got)]
            contact = sum(v for _, v in recent) > 300
            if time.time() - last > 6:
                print(f"{now()} ... {total} B total, last 12 s: {sum(v for _, v in recent)} B"
                      f"{'' if contact else '  (no contact - press the wires, LED must blink)'}")
                last = time.time()
            if contact and got == 0:
                tries += 1
                print(f"\n{now()} box was talking but went silent in the pause - prompt test #{tries}")
                if self.verify_prompt():
                    print(f"{now()} *** u-boot prompt ***")
                    return True
        print(f"{now()} no prompt (received {total} B, {tries} prompt tests)")
        return False

    # ---- probe ---------------------------------------------------------------
    def probe(self, pins, secs):
        code = ("PINS = %r\n" % (tuple(pins),)) + (PROBE % int(secs * 1000))
        out = self.exec_raw(code, b"<<PROBE-DONE>>", (secs + 3) * len(pins) + 6)
        res = {}
        for ln in out.decode("ascii", "replace").splitlines():
            if "FILES " in ln:
                print("ESP32 files:", ln.split("FILES ", 1)[1])
            if ln.startswith("PROBE "):
                try:
                    n, rest = ln[6:].split(" ", 1)
                    res[int(n)] = eval(rest)
                except Exception as e:
                    print("unparsed:", ln, e)
        if not res:
            print("probe failed:", out[-300:]); return {}
        for n in sorted(res):
            r = res[n]
            if r[0] == "ERR":
                print(f"GPIO{n}: error {r[1]}"); continue
            (lo, hi, mean, cnt, low), (_, _, mean_pd, _, _), (_, _, mean_pu, _, _), (npulse, hist) = r
            what = classify(lo, hi, mean, low, cnt, mean_pd, mean_pu, npulse, hist)
            print(f"GPIO{n}: float lo/hi/mean={lo}/{hi}/{mean} mV dips={low}/{cnt} | pull-down {mean_pd} mV | "
                  f"pull-up {mean_pu} mV | low pulses {npulse} {hist}\n        -> {what}")
        return res

    def pintest(self, pins):
        """Digital continuity per pin: returns {gpio: (low_count, high_count, verdict)}."""
        code = ("PINS = %r\n" % (tuple(pins),)) + PINTEST
        out = self.exec_raw(code, b"<<PINTEST-DONE>>", 8)
        res = {}
        for ln in out.decode("ascii", "replace").splitlines():
            if ln.startswith("PIN "):
                try:
                    n, lo, hi = [int(x) for x in ln.split()[1:4]]
                except ValueError:
                    continue
                if lo < 8 and hi > 56:
                    v = "luźny - nic nie podłączone (albo brak styku w otworze)"
                elif lo > 56 and hi > 56:
                    v = "na stałe WYSOKI - drut dotyka linii trzymanej wysoko (RX boxa, spoczynkowy TX albo 3V3)"
                elif lo < 8 and hi < 8:
                    v = "na stałe NISKI - drut dotyka masy"
                else:
                    v = f"zmienny ({lo}/64 z pull-down, {hi}/64 z pull-up) - linia się przełącza albo styk pracuje"
                res[n] = (lo, hi, v)
        return res

    # ---- contact monitor / auto repair --------------------------------------
    def monitor_until_contact(self, rx, tx, seconds, need=2):
        out = self.exec_raw(MONITOR % (rx, tx, tx), b"<<MON-READY>>", 5)
        if b"<<MON-READY>>" not in out:
            print(f"{now()} monitor failed: {out[-160:]!r}"); return False
        print(f"{now()} contact monitor (LED blinks = pad-2 wire OK); up to {seconds:.0f}s ...")
        end = time.time() + seconds; streak = 0; last = 0; acc = b""
        found = False
        while time.time() < end and not found:
            acc += self.raw(0.2)
            while b"\n" in acc:
                ln, acc = acc.split(b"\n", 1)
                if not ln.startswith(b"MON "):
                    continue
                try:
                    good, spikes, n, vtx = [int(x) for x in ln.split()[1:5]]
                except ValueError:
                    continue
                streak = streak + 1 if good >= 30 else 0
                if time.time() - last > 5 or streak:
                    print(f"{now()} pad2: bit-pulses={good} spikes={spikes} all={n} | pad3 {vtx} mV"
                          f"{'  <-- CONTACT' if streak else ''}")
                    last = time.time()
                if streak >= need:
                    found = True
                    break
        # always leave the monitor loop cleanly before anything else writes to the C3
        self.wr(ESC); self.raw(0.8)
        return found

    def auto(self, baud, tx, rx, rx_pull, minutes, action):
        """Keep the bridge up for the whole session and hammer Ctrl-C the entire time: the contact
        is intermittent, so the break must already be in progress at the moment the wire touches.
        The ESP32 LED blinks whenever bytes arrive, which is the operator's contact indicator."""
        deadline = time.time() + minutes * 60
        if not self.start_bridge(baud, tx, rx, rx_pull):
            return 3
        print(f"{now()} press the wires until the ESP32 LED blinks; the Ctrl-C storm runs for "
              f"{minutes:.0f} min")
        while time.time() < deadline:
            if self.break_in(min(120, max(10, deadline - time.time()))):
                return self.apply_fix(action)
        print(f"{now()} auto: timeout"); return 2

    def apply_fix(self, action):
        if action == "burn":
            # Minimal-risk path: the wire is intermittent, so type ONE short command and let the
            # reliable USB channel do the rest (hook + BL33 v2 are written by catch-burn.py).
            print(f"\n{now()} *** prompt reached - sending 'update' (USB burn mode) ***")
            self.send("update", 1.0)
            self.stop_bridge()
            import subprocess
            here = os.path.dirname(os.path.abspath(__file__))
            bl33 = os.path.normpath(os.path.join(here, "..", "out", "bl33-v2.img"))
            cmd = [sys.executable, os.path.join(here, "catch-burn.py"), "--wait", "90"]
            if os.path.exists(bl33):
                cmd += ["--bl33", bl33]
            print(f"{now()} running: {' '.join(cmd)}")
            r = subprocess.run(cmd)
            print(f"{now()} catch-burn.py exit {r.returncode}")
            return r.returncode
        self.send("echo console-ok", 0.6)
        self.send("printenv aml_dt", 1.0)
        if action == "drop":
            self.send("setenv preboot", 0.6)
        else:
            for p in HOOK_PARTS:
                self.send(p, 0.45)
        self.send("setenv upgrade_step 2", 0.5)
        out = self.send("saveenv", 3.0)
        hits, added = tol_find(out, "Saving Environment", 1.6)
        print(f"\n{now()} saveenv: {len(out)} B back, tolerant 'Saving Environment' hits={hits} (+{added} bits)")
        self.send("setenv zz AAAAAAAA", 0.5)
        chk = self.send("echo $zz", 1.0)
        h2, a2 = tol_find(chk, "AAAAAAAA", 1.2)
        print(f"{now()} env write-back check: hits={h2} (+{a2} bits)")
        if hits == 0 and h2 == 0:
            print(f"{now()} could not confirm the write - leaving the box AT THE PROMPT, bridge kept alive")
            return 6
        print(f"\n{now()} *** env fixed ({action}) - reset and logging the boot for 150 s ***")
        self.send("reset", 0.5)
        got = self.pump(150)
        report(got)
        return 0


def report(data):
    if not data:
        print("(no output after reset)"); return
    printable = sum(1 for b in data if 32 <= b < 127) / len(data)
    print(f"\n--- capture {len(data)} B, printable {printable:.0%} ---")
    for m in MARKERS:
        h, a = tol_find(data, m, 1.4)
        if h:
            print(f"    {m!r:24} hits={h} best +{a} bits")


def classify(lo, hi, mean, low, cnt, mean_pd, mean_pu, npulse, hist):
    HIGH = 2200   # 11 dB attenuation saturates around 2.5 V; a 3.3 V pad reads ~2500-2900
    hd = dict(hist)
    uart_like = sum(hd.get(b, 0) for b in (9, 17, 26, 35)) > max(20, 0.5 * npulse)
    spiky = hd.get(2, 0) > 0.7 * max(npulse, 1)
    if mean < 150 and mean_pu < 400:
        return "GND"
    if hi > HIGH and low > 0 and uart_like:
        return "TX of the box: real 115200 data (bit-wide low pulses) -> this is the RX wire"
    if hi > HIGH and npulse > 20 and spiky:
        return "high with only ~1-3 us spikes: no real contact (or crosstalk) -> press / solder"
    if lo > HIGH - 300 and mean > HIGH and npulse < 5:
        if mean_pd > HIGH - 400:
            return "steady 3.3 V that does not sag with pull-down: 3V3 rail -> do NOT drive"
        return "high but sags with pull-down: RX of the box (weak pull-up) -> this is the TX wire"
    if mean_pd < 300 and mean_pu > HIGH - 300 and npulse < 5:
        return "floating: nothing connected / no contact / box off"
    if hi > HIGH and low > 0:
        return "activity but pulse widths not 115200-like: baud mismatch or weak contact"
    return "unclear - repeat with the box powered and a firm contact"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default=None, help="default: first Espressif USB-JTAG port")
    ap.add_argument("--rx", type=int, default=2, help="ESP GPIO wired to the box TX (default 2)")
    ap.add_argument("--tx", type=int, default=3, help="ESP GPIO wired to the box RX (default 3)")
    ap.add_argument("--rx-pull", choices=("none", "up", "down"), default="none")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--probe-pins", default="2,3,4")
    ap.add_argument("--probe-seconds", type=float, default=2.0)
    ap.add_argument("--contact", type=float, default=0, metavar="SECONDS")
    ap.add_argument("--auto", type=float, default=0, metavar="MINUTES")
    ap.add_argument("--auto-action", choices=("burn", "fix", "drop"), default="burn")
    ap.add_argument("--loopback", action="store_true")
    ap.add_argument("--watch", type=float, default=0)
    ap.add_argument("--break", dest="brk", action="store_true")
    ap.add_argument("--break-seconds", type=float, default=40)
    ap.add_argument("--fix-hook", action="store_true")
    ap.add_argument("--drop-hook", action="store_true")
    ap.add_argument("--cmd", action="append", default=[])
    ap.add_argument("--keep", action="store_true", help="leave the bridge running on exit")
    ap.add_argument("--decode", metavar="LOGFILE", help="scan a capture for u-boot strings (offline)")
    a = ap.parse_args()

    if a.decode:
        data = open(a.decode, "rb").read()
        print(f"{a.decode}: {len(data)} B")
        report(data[-200000:])
        return 0

    ads = list_adapters()
    if not ads:
        print("nie znaleziono żadnego adaptera szeregowego (USB-TTL ani ESP32)"); return 5
    print("dostępne adaptery: " + ", ".join(f"{d} = {desc} [{m}]" for d, m, desc in ads))
    port = a.port or detect_port()
    mode = next((m for d, m, _ in ads if d == port), "direct")
    logpath = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out", f"serial-{port}.log"))
    L = Link(port, logpath, mode=mode, baud=a.baud)
    print(f"{now()} {port} ({mode}); wyjście boxa -> {logpath}")
    if a.probe:
        L.probe([int(x) for x in a.probe_pins.split(",")], a.probe_seconds)
        return 0
    if a.contact:
        L.monitor_until_contact(a.rx, a.tx, a.contact, need=10 ** 9)
        return 0
    if a.auto:
        rc = L.auto(a.baud, a.tx, a.rx, a.rx_pull, a.auto, a.auto_action)
        if rc != 6:
            L.stop_bridge()
        return rc
    if not L.start_bridge(a.baud, a.tx, a.rx, a.rx_pull):
        return 3
    rc = 0
    try:
        if a.loopback:
            L.raw(0.3)
            msg = b"loopback-test"
            L.wr(msg + b"\n"); got = L.raw(0.6)
            L.wr(b"\x03"); got += L.raw(0.3)
            t_ok = msg in got; c_ok = b"\x03" in got
            print(f"{now()} loopback {'OK' if t_ok and c_ok else 'FAILED'} "
                  f"(text {'seen' if t_ok else 'missing'}, Ctrl-C {'seen' if c_ok else 'missing'}) {got[:40]!r}")
            return 0 if (t_ok and c_ok) else 4
        if a.watch:
            got = L.pump(a.watch)
            report(got)
        if a.brk:
            if not L.break_in(a.break_seconds):
                return 2
        if a.fix_hook or a.drop_hook:
            return L.apply_fix("drop" if a.drop_hook else "fix")
        for c in a.cmd:
            L.send(c, 1.5)
    finally:
        if not a.keep:
            L.stop_bridge()
    return rc


if __name__ == "__main__":
    sys.exit(main())
