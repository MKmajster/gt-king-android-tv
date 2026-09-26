#!/usr/bin/env python3
"""Re-pack an existing USB Burning Tool package with a different `bootloader` PARTITION item.

    python3 repack-package-bootloader.py <in.img> <out.img> <u-boot.bin for PARTITION bootloader> <aml_image_packer> [--drop-env]

Used to put the hooked stock bootloader (patch-stock-bl33-env.py) into packages whose build
outputs are gone (the vanilla build). The USB DDR/UBOOT items (the u-boot the tool itself runs
during the burn) stay as they are; only what gets written to the eMMC bootloader area changes.
--drop-env removes the `env` item (the tool's final saveenv overwrites it anyway).
"""
import os
import shutil
import struct
import subprocess
import sys
import tempfile

NUL = bytes([0])


def items(path):
    f = open(path, "rb")
    crc, ver, magic, imgsz, align, n = struct.unpack("<IIIQII", f.read(64)[:28])
    isz, tl = (0x80, 32) if ver == 1 else (0x240, 256)
    out = []
    for i in range(n):
        it = f.read(isz)
        iid, ft, cur, off, sz = struct.unpack("<IIQQQ", it[:32])
        mt = it[32:32 + tl].split(NUL)[0].decode()
        st = it[32 + tl:32 + 2 * tl].split(NUL)[0].decode()
        out.append((mt, st, off, sz))
    return f, out


def main():
    src, dst, ub, packer = sys.argv[1:5]
    drop_env = "--drop-env" in sys.argv
    f, its = items(src)
    stage = tempfile.mkdtemp(prefix="repack-", dir=os.path.expanduser("~"))
    names = {}      # (offset,size) -> file name, so items sharing data share one file
    cfg = []
    for mt, st, off, sz in its:
        if mt == "PARTITION" and st == "env" and drop_env:
            continue
        key = (off, sz)
        if key not in names:
            base = {"USB": "u-boot.bin", "UBOOT": "u-boot.bin", "ini": "aml_sdc_burn.ini", "dtb": "dtb.img",
                    "conf": "platform.conf"}.get(mt, st + ".img")
            if mt == "PARTITION" and st == "_aml_dtb":
                base = "dtb.img"
            if mt == "PARTITION" and st == "bootloader":
                base = "u-boot.bin"
            names[key] = base
            f.seek(off)
            with open(os.path.join(stage, base), "wb") as o:
                left = sz
                while left:
                    chunk = f.read(min(left, 1 << 24))
                    o.write(chunk)
                    left -= len(chunk)
        name = names[key]
        if mt == "PARTITION" and st == "bootloader":
            shutil.copy(ub, os.path.join(stage, "u-boot-hook.bin"))
            name = "u-boot-hook.bin"
        cfg.append('file="%s"\t\tmain_type="%s"\t\tsub_type="%s"' % (name, mt, st))
    open(os.path.join(stage, "image.cfg"), "w").write("[LIST_NORMAL]" + chr(10) + chr(10).join(cfg) + chr(10))
    print(chr(10).join(cfg))
    subprocess.run([packer, "-r", os.path.join(stage, "image.cfg"), stage + "/", dst], check=True)
    shutil.rmtree(stage)
    print("wrote", dst, os.path.getsize(dst))


if __name__ == "__main__":
    main()
