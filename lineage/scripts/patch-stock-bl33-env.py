#!/usr/bin/env python3
"""Put the chainload hook into the stock Beelink u-boot's COMPILED-IN default environment.

    python3 patch-stock-bl33-env.py <stock bootloader.img|u-boot.bin> <aml_encrypt_g12b> <out-dir>

Why: the USB Burning Tool's own u-boot ends every burn with a `saveenv` of the DEFAULT environment
(and the stock u-boot repeats `defenv_reserv` on its first boot), so an `env` partition image in
the package never survives - after the 2026-09-25 flash the box came up with the stock `preboot`,
booted the LineageOS kernel itself (no CPU clock setup -> cpufreq BUG at 1.8 s) and looped until
the hook was re-installed over UART. With the hook as the default `preboot`, every env reset
re-creates it. Nothing else in the bootloader changes: same BL2 (DDR training), BL30/31/32, same
u-boot code; only the 147-byte `preboot=` string inside BL33 is replaced (padded with spaces).

Stock BL33 layout (aml_encrypt_g12b --bl3sig --level v3 --compress lz4, verified byte-for-byte:
re-signing the unmodified decompressed BL33 reproduces the stock LZ4 block exactly):
    +0x000  @AML header (0x290 bytes): +0x20 payload size, +0x28 header size, +0x30 sha256(payload)
    +0x290  "LZ4C" container: blksz, total (decompressed) size, block length, date, hashes (0x80)
    +0x310  one raw LZ4 block
Outputs in <out-dir>: u-boot-stock+hook.bin (u-boot.bin form), bootloader-stock+hook.img (512-byte
prefix, eMMC `bootloader` partition form), sd-hook-test.img (4 MiB raw image for a microSD: the
BootROM boots the card first, so the patched bootloader can be tried without touching the eMMC).
"""
import hashlib
import os
import re
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hook  # noqa: E402  (the one hook definition)

AML = b"@AML"
TOC = b"\x01\x00\x64\xaa"


def lz4_block(src, limit):
    out = bytearray()
    i, n = 0, len(src)
    while i < n and len(out) < limit:
        tok = src[i]
        i += 1
        lit = tok >> 4
        if lit == 15:
            while True:
                b = src[i]
                i += 1
                lit += b
                if b != 255:
                    break
        out += src[i:i + lit]
        i += lit
        if i >= n:
            break
        off = src[i] | (src[i + 1] << 8)
        i += 2
        ml = tok & 15
        if ml == 15:
            while True:
                b = src[i]
                i += 1
                ml += b
                if b != 255:
                    break
        ml += 4
        for _ in range(ml):
            out.append(out[-off])
    return bytes(out)


def main():
    src, tool, outdir = sys.argv[1:4]
    d = open(src, "rb").read()
    if d[0x210:0x214] == AML and d[0x10:0x14] != AML:
        d = d[0x200:]                                   # bootloader.img form
    assert d[0x10:0x14] == AML and d[0x10010:0x10014] == TOC, "not an Amlogic g12 u-boot.bin"
    # find the BL33 entry = the largest FIP TOC entry
    base = 0x10000
    entries = []
    for i in range(16):
        e = base + 0x10 + 16 + i * 40
        if d[e:e + 16] == bytes(16):
            break
        off, size, _ = struct.unpack("<QQQ", d[e + 16:e + 40])
        entries.append((base + off, size))
    off, size = max(entries, key=lambda x: x[1])
    entry = d[off:off + size]
    assert entry[0x10:0x14] == AML and entry[0x290:0x294] == b"LZ4C", "BL33 entry layout unexpected"
    total = struct.unpack("<I", entry[0x298:0x29c])[0]
    blen = struct.unpack("<I", entry[0x29c:0x2a0])[0]
    dec = bytearray(lz4_block(entry[0x310:0x310 + blen], total))
    assert len(dec) == total, "decompression short"
    m = re.search(rb"preboot=[^\x00]*", dec)
    room = m.end() - m.start() - len(b"preboot=")
    new = hook.HOOK.encode()
    assert len(new) <= room, "hook (%d) longer than the stock preboot (%d)" % (len(new), room)
    print("stock default preboot (%d): %s" % (room, dec[m.start() + 8:m.end()].decode()))
    dec[m.start():m.end()] = b"preboot=" + new + b" " * (room - len(new))
    assert dec.count(b"preboot=") == 1

    os.makedirs(outdir, exist_ok=True)
    raw = os.path.join(outdir, "bl33-stock-hook.bin")
    enc = os.path.join(outdir, "bl33-stock-hook.enc")
    open(raw, "wb").write(dec)
    subprocess.run([tool, "--bl3sig", "--input", raw, "--output", enc, "--level", "v3", "--type", "bl33",
                    "--compress", "lz4"], check=True)
    e = open(enc, "rb").read()
    a = e.find(AML) - 0x10                              # skip the tool's @KEY wrapper
    new_entry = e[a:a + size]
    psize = struct.unpack("<I", new_entry[0x20:0x24])[0]
    hsize = struct.unpack("<I", new_entry[0x28:0x2c])[0]
    assert len(new_entry) == size and hsize == 0x290 and psize == size - 0x290, "entry size changed"
    assert hashlib.sha256(new_entry[hsize:hsize + psize]).digest() == new_entry[0x30:0x50], "payload sha"
    nblen = struct.unpack("<I", new_entry[0x29c:0x2a0])[0]
    check = lz4_block(new_entry[0x310:0x310 + nblen], total)
    assert check == bytes(dec), "re-decompressed image differs"
    out = bytearray(d)
    out[off:off + size] = new_entry
    ub = os.path.join(outdir, "u-boot-stock+hook.bin")
    bl = os.path.join(outdir, "bootloader-stock+hook.img")
    sd = os.path.join(outdir, "sd-hook-test.img")
    open(ub, "wb").write(out)
    open(bl, "wb").write(bytes(512) + out)
    img = bytes(512) + bytes(out)
    open(sd, "wb").write(img + bytes(4 * 1024 * 1024 - len(img)))
    for p in (ub, bl, sd):
        print("%s  %d bytes  sha256 %s" % (os.path.basename(p), os.path.getsize(p), hashlib.sha256(open(p, "rb").read()).hexdigest()))
    print("new default preboot: %s" % re.search(rb"preboot=[^\x00]*", check).group()[8:].decode().strip())


if __name__ == "__main__":
    main()
