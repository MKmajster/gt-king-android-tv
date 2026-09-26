"""Try many baud settings on a suspicious USB-TTL adapter and report which one yields readable
u-boot/kernel text (for clones whose baud generator is off by a fixed factor)."""
import serial, sys, time, re
port = sys.argv[1] if len(sys.argv) > 1 else "COM8"
secs = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0
KEYS = re.compile(rb"U-Boot|BL2|bl2|TE:|G12B|DDR|boot|Linux|init|galilei|preboot|Starting|reset|mmc", re.I)
for baud in (1200, 2400, 4800, 9600, 14400, 19200, 28800, 38400, 57600, 76800, 115200, 230400):
    try:
        s = serial.Serial(); s.port = port; s.baudrate = baud; s.timeout = 0.1; s.dtr = False; s.rts = False; s.open()
    except Exception as e:
        print(f"{baud:7d}: open failed {e}"); continue
    s.reset_input_buffer(); t0 = time.time(); buf = b""
    while time.time() - t0 < secs: buf += s.read(65536)
    s.close()
    if not buf:
        print(f"{baud:7d}: silence"); continue
    pr = sum(1 for c in buf if 32 <= c < 127 or c in (10, 13)) / len(buf)
    hits = len(KEYS.findall(buf))
    sample = re.sub(rb"[^\x20-\x7e\n]", b"?", buf[:300]).decode()
    print(f"{baud:7d}: {len(buf)/secs:8.0f} B/s printable {100*pr:3.0f}% keywords {hits:3d} | {sample[:120]!r}")
