#!/usr/bin/env python3
"""Pack several DTBs into an Amlogic multi-DTB v2 container ("AML_" magic), the format the stock
u-boot's multi-dtb tool (common/aml_dt.c) and the kernel's amlmmc dtb driver understand.

    py -3.14 make-multi-dtb.py OUT.img galilei.dtb stock-w400_b.dtb ...

Each DTB's entry (soc, platform, variant) comes from its own /amlogic-dt-id ("g12b_s922x_galilei"
-> g12b / s922x / galilei). Layout copied from the stock Beelink image: 12-byte header, 56-byte
entries (3 x 16-byte id fields stored as big-endian-text u32 words, space padded, + offset + size),
DTBs at 2 KiB aligned offsets from 0x800. Why: the stock u-boot reads _aml_dtb for its OWN board
init (display, eth, keys); with our single galilei DTB it hangs in the ethernet init on a cold boot
(2026-09-24), so it must keep finding its g12b_w400_b while our galilei u-boot finds g12b_s922x_galilei.
"""
import struct, sys, re

def dt_id(d):
    m = re.search(rb"g12b_[a-z0-9]+_[a-z0-9]+", d)
    if not m:
        raise SystemExit("no amlogic-dt-id in dtb")
    return m.group().decode()

def field(s):
    s = s.encode().ljust(16, b" ")
    return b"".join(s[i:i+4][::-1] for i in range(0, 16, 4))  # u32 words, text order -> LE bytes

def pack(out, paths):
    dtbs = [open(p, "rb").read() for p in paths]
    for p, d in zip(paths, dtbs):
        assert d[:4] == b"\xd0\x0d\xfe\xed", f"{p}: not an FDT"
        assert struct.unpack(">I", d[4:8])[0] == len(d), f"{p}: totalsize != file size"
    hdr = b"AML_" + struct.pack("<II", 2, len(dtbs))
    off = 0x800
    entries = b""; body = b""
    for p, d in zip(paths, dtbs):
        soc, plat, vari = dt_id(d).split("_", 2)
        size = (len(d) + 2047) // 2048 * 2048
        entries += field(soc) + field(plat) + field(vari) + struct.pack("<II", off, size)
        body += d + b"\0" * (size - len(d))
        print(f"  {p}: {soc}/{plat}/{vari} at 0x{off:x} size 0x{size:x} (fdt {len(d)})")
        off += size
    head = hdr + entries
    assert len(head) <= 0x800
    img = head + b"\0" * (0x800 - len(head)) + body
    open(out, "wb").write(img)
    print(f"{out}: {len(img)} bytes, {len(dtbs)} dtbs")

if __name__ == "__main__":
    pack(sys.argv[1], sys.argv[2:])
