#!/usr/bin/env python3
"""Send a file to u-boot 'loady' over the serial console (YMODEM, 1 KiB blocks, CRC16).

    py -3.14 uart-ymodem.py --port COM9 --addr 0x1000000 file.bin [--cmd "store dtb write 0x1000000 0x2f000"] [--reset] [--after 120]

Types 'loady <addr>' at the prompt, streams the file, then optionally runs commands (e.g. the
store write) and 'reset'. 192 KiB takes ~25 s at 115200. Everything received is appended to
lineage/out/serial-<port>.log like serial-console.py.

If the receiver loses us mid-transfer (it starts polling with 'C' again or goes silent - seen
2026-09-24 after 27 blocks), the session is cancelled (CAN) and 'loady' is started again, up to
3 sessions.
"""
import argparse, os, sys, time
import serial

SOH, STX, EOT, ACK, NAK, CAN, CRC = 0x01, 0x02, 0x04, 0x06, 0x15, 0x18, 0x43


class Restart(Exception):
    pass


def crc16(data):
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return crc


def now():
    return time.strftime("%H:%M:%S")


class Sender:
    def __init__(self, port, logpath):
        self.s = serial.Serial(port, 115200, timeout=0.05)
        self.log = open(logpath, "ab")

    def pump(self, secs):
        end = time.time() + secs; got = b""
        while time.time() < end:
            d = self.s.read(4096)
            if d:
                got += d; self.log.write(d); self.log.flush()
        return got

    def send_cmd(self, text, wait=1.0):
        self.s.write(text.encode() + b"\n"); self.s.flush()
        out = self.pump(wait)
        sys.stdout.write(out.decode("ascii", "replace")); sys.stdout.flush()
        return out

    def wait_byte(self, wanted, secs):
        end = time.time() + secs
        while time.time() < end:
            b = self.s.read(1)
            if b:
                self.log.write(b); self.log.flush()
                if b[0] in wanted:
                    return b[0]
        return None

    def send_block(self, seq, payload):
        hdr = bytes([STX if len(payload) > 128 else SOH, seq & 0xFF, (~seq) & 0xFF])
        pad = 1024 if len(payload) > 128 else 128
        payload = payload + b"\x1a" * (pad - len(payload))
        frame = hdr + payload + crc16(payload).to_bytes(2, "big")
        polls = 0
        for attempt in range(10):
            self.s.write(frame); self.s.flush()
            r = self.wait_byte((ACK, NAK, CAN, CRC), 10)
            if r == ACK:
                return
            if r == CAN:
                raise SystemExit("receiver cancelled")
            if r is None:
                raise Restart(f"block {seq}: receiver silent")
            if r == CRC and seq != 0:
                polls += 1      # the receiver is polling for a (re)start: it lost us
                if polls >= 3:
                    raise Restart(f"block {seq}: receiver keeps polling with C")
        raise SystemExit(f"block {seq}: no ACK after 10 tries")

    def transfer(self, addr, path, data):
        for session in range(3):
            try:
                print(f"{now()} loady {addr}: {len(data)} bytes (session {session + 1})", flush=True)
                self.s.write(f"loady {addr}\n".encode()); self.s.flush()
                if self.wait_byte((CRC, NAK), 15) is None:
                    raise SystemExit("no C/NAK from loady")
                name = os.path.basename(path).encode()
                self.send_block(0, name + b"\0" + str(len(data)).encode() + b"\0")   # YMODEM header
                if self.wait_byte((CRC,), 10) is None:
                    raise SystemExit("no C after header")
                seq = 1; t0 = time.time()
                for off in range(0, len(data), 1024):
                    self.send_block(seq, data[off:off + 1024]); seq += 1
                    if seq % 20 == 0:
                        print(f"  {off + 1024}/{len(data)} B", flush=True)
                for _ in range(3):
                    self.s.write(bytes([EOT])); self.s.flush()
                    if self.wait_byte((ACK, NAK), 5) == ACK:
                        break
                self.wait_byte((CRC, NAK), 5)
                self.send_block(0, b"\0" * 128)   # end-of-session null header
                print(f"{now()} sent in {time.time() - t0:.1f}s", flush=True)
                tail = self.pump(2.0) + self.pump(2.0)
                sys.stdout.write(tail.decode("ascii", "replace")); sys.stdout.flush()
                if b"Total Size" not in tail:
                    print("WARNING: no '## Total Size' line from loady", flush=True)
                return
            except Restart as e:
                print(f"{now()} {e} -> cancelling and restarting the transfer", flush=True)
                self.s.write(bytes([CAN]) * 5); self.s.flush(); self.pump(2.0)
                self.s.write(b"\n"); self.pump(1.0)
        raise SystemExit("transfer failed after 3 sessions")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", required=True)
    ap.add_argument("--addr", required=True)
    ap.add_argument("file")
    ap.add_argument("--cmd", action="append", default=[])
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--after", type=float, default=0, help="seconds to keep logging after the last command")
    a = ap.parse_args()
    data = open(a.file, "rb").read()
    logpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out", f"serial-{a.port}.log")
    x = Sender(a.port, logpath)
    x.send_cmd("", 0.4)
    x.transfer(a.addr, a.file, data)
    for c in a.cmd:
        x.send_cmd(c, 2.0)
    if a.reset:
        x.send_cmd("reset", 1.0)
    if a.after:
        sys.stdout.write(x.pump(a.after).decode("ascii", "replace"))


if __name__ == "__main__":
    main()
