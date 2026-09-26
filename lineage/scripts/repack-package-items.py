#!/usr/bin/env python3
"""Re-pack a USB Burning Tool package with PARTITION items replaced, dropped or added.
    python3 repack-package-items.py <in.img> <out.img> <aml_image_packer>
        [--dtb FILE]            replace both the tool's "dtb meson1" and PARTITION _aml_dtb
        [--set NAME=FILE ...]   replace PARTITION NAME
        [--drop NAME ...]       remove PARTITION NAME
        [--add NAME=FILE ...]   add PARTITION NAME (inserted before "bootloader")
Everything else (USB DDR/UBOOT, aml_sdc_burn, ini, platform.conf, the hooked bootloader, bl33 ...)
is copied unchanged. Sparse images are detected by the packer. Stage dir: ~/repack-items-*.
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
    for _ in range(n):
        it = f.read(isz)
        iid, ft, cur, off, sz = struct.unpack("<IIQQQ", it[:32])
        mt = it[32:32 + tl].split(NUL)[0].decode()
        st = it[32 + tl:32 + 2 * tl].split(NUL)[0].decode()
        out.append((mt, st, off, sz))
    return f, out


def main():
    a = sys.argv[1:]
    src, dst, packer = a[:3]
    dtb, sets, drops, adds = None, {}, set(), []
    i = 3
    while i < len(a):
        opt, val = a[i], a[i + 1]
        if opt == "--dtb":
            dtb = val
        elif opt == "--set":
            k, v = val.split("=", 1); sets[k] = v
        elif opt == "--drop":
            drops.add(val)
        elif opt == "--add":
            k, v = val.split("=", 1); adds.append((k, v))
        else:
            raise SystemExit("unknown option " + opt)
        i += 2
    f, its = items(src)
    stage = tempfile.mkdtemp(prefix="repack-items-", dir=os.path.expanduser("~"))
    names, cfg = {}, []

    def link(path, name):
        dst_ = os.path.join(stage, name)
        if not os.path.exists(dst_):
            os.symlink(os.path.abspath(path), dst_)
        return name

    def extract(off, sz, base):
        key = (off, sz)
        if key not in names:
            names[key] = base
            f.seek(off)
            with open(os.path.join(stage, base), "wb") as o:
                left = sz
                while left:
                    chunk = f.read(min(left, 1 << 24)); o.write(chunk); left -= len(chunk)
        return names[key]

    for mt, st, off, sz in its:
        if mt == "PARTITION" and st in drops:
            continue
        if mt == "PARTITION" and st == "bootloader":
            for k, v in adds:
                cfg.append('file="%s"\t\tmain_type="PARTITION"\t\tsub_type="%s"' % (link(v, k + ".img"), k))
            adds = []
        if (mt == "dtb" or (mt == "PARTITION" and st == "_aml_dtb")) and dtb:
            name = link(dtb, "dtb-new.img")
        elif mt == "PARTITION" and st in sets:
            name = link(sets[st], st + "-new.img")
        else:
            base = {"USB": "u-boot.bin", "UBOOT": "u-boot.bin", "ini": "aml_sdc_burn.ini", "dtb": "dtb.img",
                    "conf": "platform.conf"}.get(mt, st + ".img")
            if mt == "PARTITION" and st == "bootloader":
                base = "u-boot-hook.bin"
            name = extract(off, sz, base)
        cfg.append('file="%s"\t\tmain_type="%s"\t\tsub_type="%s"' % (name, mt, st))
    for k, v in adds:   # no bootloader item: append at the end
        cfg.append('file="%s"\t\tmain_type="PARTITION"\t\tsub_type="%s"' % (link(v, k + ".img"), k))
    open(os.path.join(stage, "image.cfg"), "w").write("[LIST_NORMAL]" + chr(10) + chr(10).join(cfg) + chr(10))
    print(chr(10).join(cfg))
    subprocess.run([packer, "-r", os.path.join(stage, "image.cfg"), stage + "/", dst], check=True)
    shutil.rmtree(stage)
    print("wrote", dst, os.path.getsize(dst))


if __name__ == "__main__":
    main()
