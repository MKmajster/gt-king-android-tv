"""Resilient serial logger: waits for a USB-TTL adapter (FTDI/CH340/CP210x/PL2303), logs everything
to lineage/out/serial-<PORT>.log, prints a 5 s summary with the last readable lines, and reopens
the port whenever the adapter disappears. DTR/RTS deasserted (no auto-reset pulses)."""
import serial, serial.tools.list_ports, sys, time
VIDS = {0x0403, 0x1A86, 0x10C4, 0x067B}
secs = float(sys.argv[1]) if len(sys.argv) > 1 else 1800
baud = int(sys.argv[2]) if len(sys.argv) > 2 else 115200
def find():
    for p in serial.tools.list_ports.comports():
        if p.vid in VIDS: return p.device
    return None
t0 = time.time(); total = 0; s = None; port = None; announced = False
while time.time() - t0 < secs:
    if s is None:
        port = find()
        if not port:
            if not announced: print(f"--- {time.strftime('%H:%M:%S')} no USB-TTL adapter present, waiting", flush=True); announced = True
            time.sleep(1); continue
        try:
            s = serial.Serial(); s.port = port; s.baudrate = baud; s.timeout = 0.2; s.dtr = False; s.rts = False; s.open()
            log = open(f"lineage/out/serial-{port}.log", "ab"); announced = False
            print(f"--- {time.strftime('%H:%M:%S')} opened {port}", flush=True)
        except Exception as e:
            print(f"--- {time.strftime('%H:%M:%S')} open {port} failed: {e}", flush=True); s = None; time.sleep(2); continue
        last = time.time(); buf = b""
    try:
        d = s.read(4096)
    except Exception as e:
        print(f"--- {time.strftime('%H:%M:%S')} {port} lost ({e.__class__.__name__}), waiting for it to come back", flush=True)
        try: s.close()
        except Exception: pass
        s = None; time.sleep(1); continue
    if d:
        buf += d; total += len(d); log.write(d); log.flush()
    if time.time() - last >= 5:
        last = time.time()
        if buf:
            pr = sum(1 for c in buf if 32 <= c < 127 or c in (10, 13))
            lines = [l for l in buf.decode("ascii", "replace").replace("�", "?").splitlines() if l.strip()][-12:]
            print(f"--- {time.strftime('%H:%M:%S')} +{len(buf)} B (total {total}), printable {100*pr/len(buf):.0f}%", flush=True)
            for l in lines: print("   " + l[:160], flush=True)
            buf = b""
        else:
            print(f"--- {time.strftime('%H:%M:%S')} silence (total {total})", flush=True)
