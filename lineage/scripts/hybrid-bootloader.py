#!/usr/bin/env python3
"""
Build a "hybrid" Amlogic G12B bootloader for the Beelink GT-King Pro:
stock Beelink BL2 (which carries the board's LPDDR4 timing and is known to
initialise this box's DDR) + the FIP (BL30/BL31/BL33 + DDR firmware) from the
LineageOS u-boot build.

Layout of an Amlogic G12 u-boot.bin (aml_encrypt_g12b --bootmk, level v3):
    0x00000  BL2 (bl2.n.bin.sig), 64 KiB, "@AML" header at +0x10
    0x10000  FIP: 16-byte header, TOC (magic aa640001) at +0x10, DDR firmware,
             then BL30 / BL31 / (BL32) / BL33 as "@AML"-headed blobs
The eMMC "bootloader" partition image (bootloader.img) is the same with 512
zero bytes in front (u-boot.bin is written with dd seek=1 bs=512).

Usage:
  hybrid-bootloader.py <stock bootloader.img|u-boot.bin> <lineage u-boot.bin> <out.bin> [fip-dir]

Outputs <out.bin> (u-boot.bin form, no 512-byte prefix) plus <out.bin>.sd.bin
(512-byte prefix, for SD/eMMC dd) and <out.bin>.usb.bl2 / .usb.tpl for
pyamlboot RAM boot. With [fip-dir] (e.g. hardware/amlogic/u-boot_build/
fip-radxa-zero2) it also reports whether the DDR firmware blobs embedded in
the stock image are byte-identical to the ones the LineageOS FIP uses.
"""
import os
import struct
import sys

AML = b"@AML"
TOC = b"\x01\x00\x64\xaa"
BL2_SIZE = 0x10000


def die(msg):
    print("error: " + msg, file=sys.stderr)
    sys.exit(1)


def load_uboot(path):
    d = open(path, "rb").read()
    if d[0x210:0x214] == AML and d[0x10:0x14] != AML:
        d = d[0x200:]                      # bootloader.img form
    if d[0x10:0x14] != AML:
        die("%s: no @AML header at 0x10 (not an Amlogic u-boot.bin)" % path)
    if d[BL2_SIZE + 0x10:BL2_SIZE + 0x14] != TOC:
        die("%s: no FIP TOC at 0x%x" % (path, BL2_SIZE + 0x10))
    return d


def toc_entries(d):
    base = BL2_SIZE + 0x10
    out = []
    for i in range(16):
        e = base + 16 + i * 40
        uuid = d[e:e + 16]
        if uuid == b"\x00" * 16:
            break
        off, size, flags = struct.unpack("<QQQ", d[e + 16:e + 40])
        out.append((uuid.hex(), off, size))
    return out


def describe(name, d):
    print("%s: %d bytes, BL2 header %s" % (name, len(d), d[0x10:0x30].hex()))
    for uuid, off, size in toc_entries(d):
        blob = d[BL2_SIZE + off:BL2_SIZE + off + 0x20]
        tag = "@AML" if blob[:4] == AML else blob[:4].hex()
        print("   toc %s off 0x%06x size 0x%06x %s" % (uuid[:8], off, size, tag))


def check_ddrfw(stock, fipdir):
    names = ["ddr4_1d.fw", "ddr4_2d.fw", "ddr3_1d.fw", "piei.fw", "lpddr4_1d.fw",
             "lpddr4_2d.fw", "diag_lpddr4.fw", "aml_ddr.fw", "lpddr3_1d.fw"]
    print("DDR firmware from %s vs. stock image:" % fipdir)
    for n in names:
        p = os.path.join(fipdir, n)
        if not os.path.isfile(p):
            continue
        fw = open(p, "rb").read()
        body = fw[0x100:0x400]              # skip the small per-file header
        idx = stock.find(body)
        if idx < 0:
            print("   %-16s NOT found in stock image" % n)
            continue
        start = idx - 0x100
        same = stock[start:start + len(fw)] == fw
        print("   %-16s found at 0x%06x, %s" % (n, start, "identical" if same else "DIFFERENT"))


def main():
    if len(sys.argv) not in (4, 5):
        die(__doc__)
    stock = load_uboot(sys.argv[1])
    lineage = load_uboot(sys.argv[2])
    out = sys.argv[3]
    describe("stock", stock)
    describe("lineage", lineage)
    if len(sys.argv) == 5:
        check_ddrfw(stock, sys.argv[4])

    hybrid = stock[:BL2_SIZE] + lineage[BL2_SIZE:]
    open(out, "wb").write(hybrid)
    open(out + ".sd.bin", "wb").write(b"\x00" * 512 + hybrid)
    open(out + ".usb.bl2", "wb").write(hybrid[:BL2_SIZE])
    open(out + ".usb.tpl", "wb").write(hybrid[BL2_SIZE:])
    print("wrote %s (+ .sd.bin, .usb.bl2, .usb.tpl): stock BL2 + lineage FIP, %d bytes" % (out, len(hybrid)))


if __name__ == "__main__":
    main()
