#!/usr/bin/env python3
"""Build an Amlogic u-boot env partition image (8 MiB, crc32 + "key=value\\0"... "\\0") from a base
image plus overrides, so the USB Burning Tool package can ship the chainload hook itself
(PARTITION env) and nobody needs a serial console after flashing.

    python3 make-env-image.py <base env.img> <out env.img> [KEY=VALUE ...] [--delete KEY ...]
    python3 make-env-image.py --print <env.img>

Base = the env dumped from the working box (lineage/out/env-current.img: SlimBox/factory
variables + the hook installed by serial-console.py --fix-hook). The CRC covers the first 0x10000 - 4
bytes (CONFIG_ENV_SIZE = 64 KiB, verified against the factory env.img), little-endian; the 8 MiB
partition image is zero padded after that.
"""
import sys
import zlib

ENV_SIZE = 0x10000      # CONFIG_ENV_SIZE: the crc32 covers 0x10000-4 bytes (verified on the factory env.img)
PART_SIZE = 0x800000    # the env partition itself; the rest is zero padding


def parse(data):
    body = data[4:]
    end = body.find(b"\0\0")
    env = {}
    for item in body[:end].split(b"\0"):
        if b"=" in item:
            k, v = item.split(b"=", 1)
            env[k.decode("latin1")] = v.decode("latin1")
    return env


def build(env):
    body = b"".join(("%s=%s" % (k, v)).encode("latin1") + b"\0" for k, v in sorted(env.items())) + b"\0"
    if len(body) > ENV_SIZE - 4:
        raise SystemExit("env too large: %d > %d" % (len(body), ENV_SIZE - 4))
    body = body.ljust(ENV_SIZE - 4, b"\0")
    crc = zlib.crc32(body) & 0xFFFFFFFF
    return (crc.to_bytes(4, "little") + body).ljust(PART_SIZE, b"\0")


def main():
    args = sys.argv[1:]
    if args and args[0] == "--print":
        env = parse(open(args[1], "rb").read())
        for k in sorted(env):
            print("%s=%s" % (k, env[k]))
        return
    base, out = args[0], args[1]
    data = open(base, "rb").read()
    stored = int.from_bytes(data[:4], "little")
    calc = zlib.crc32(data[4:ENV_SIZE]) & 0xFFFFFFFF
    print("base crc32 stored %08x calculated %08x %s" % (stored, calc, "OK" if stored == calc else "MISMATCH (base is not a plain env image?)"))
    env = parse(data)
    deletes = False
    for a in args[2:]:
        if a == "--delete":
            deletes = True
        elif deletes:
            env.pop(a, None)
        else:
            k, v = a.split("=", 1)
            env[k] = v
    img = build(env)
    open(out, "wb").write(img)
    check = parse(img)
    print("wrote %s: %d vars, preboot=%s" % (out, len(check), check.get("preboot", "<none>")[:90]))


if __name__ == "__main__":
    main()
