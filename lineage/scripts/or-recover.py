#!/usr/bin/env python3
r"""Recover u-boot console text captured over a marginal UART wire.

A resistive pad contact only ever turns received 0 bits into 1 bits ('timeout' arrives as
'wimeouv'), so a byte is always a bit-superset of the original. The GT-King PRO is stuck in a
boot loop, which means the same text is transmitted over and over: ANDing several occurrences of
the same passage removes the noise, because a bit is only kept when every copy had it set.

    py -3.14 lineage/scripts/or-recover.py lineage/out/serial-COM4.log
    py -3.14 lineage/scripts/or-recover.py --anchor "U-Boot 20" --span 4000 <log>

Prints the recovered text plus how many copies were averaged.
"""
import argparse, sys
from collections import Counter


def popcount(x):
    return bin(x).count("1")


def tol_positions(buf, needle, max_added_per_char=2.2):
    n = needle.encode() if isinstance(needle, str) else needle
    L = len(n); limit = max_added_per_char * L
    out = []
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
            out.append((i, added))
    return out


def and_merge(chunks):
    if not chunks:
        return b""
    L = min(len(c) for c in chunks)
    out = bytearray(L)
    for i in range(L):
        v = 0xFF
        for c in chunks:
            v &= c[i]
        out[i] = v
    return bytes(out)


def score(text):
    """How much of the result looks like console output."""
    if not text:
        return 0.0
    ok = sum(1 for b in text if 32 <= b < 127 or b in (10, 13))
    return ok / len(text)


def find_period(buf, minp=2000, maxp=60000, step=13):
    """Best repeat period, judged by how well buf[i] AND buf[i+p] stays printable."""
    best = (0.0, None)
    for p in range(minp, min(maxp, len(buf) // 2), step):
        s = 0; n = 0
        for i in range(0, len(buf) - p, max(1, (len(buf) - p) // 400)):
            v = buf[i] & buf[i + p]
            if 32 <= v < 127 or v in (10, 13):
                s += 1
            n += 1
        if n and s / n > best[0]:
            best = (s / n, p)
    return best


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("log")
    ap.add_argument("--anchor", default="U-Boot 20", help="text that starts every repetition")
    ap.add_argument("--span", type=int, default=3000, help="bytes to recover after each anchor")
    ap.add_argument("--tail", type=int, default=400000, help="only use the last N bytes of the log")
    ap.add_argument("--max-added", type=float, default=2.2)
    ap.add_argument("--period", action="store_true", help="also report the detected loop period")
    a = ap.parse_args()

    buf = open(a.log, "rb").read()[-a.tail:]
    print(f"{a.log}: {len(buf)} B analysed")

    hits = tol_positions(buf, a.anchor, a.max_added)
    # keep the cleanest hit per neighbourhood
    kept = []
    for pos, added in sorted(hits):
        if kept and pos - kept[-1][0] < 500:
            if added < kept[-1][1]:
                kept[-1] = (pos, added)
            continue
        kept.append((pos, added))
    print(f"anchor {a.anchor!r}: {len(kept)} occurrences (added bits: "
          f"{[x[1] for x in kept][:12]})")

    if len(kept) < 2:
        print("not enough repetitions to merge; try a shorter --anchor or a bigger --max-added")
        if a.period:
            q, p = find_period(buf)
            print(f"best period guess: {p} B (quality {q:.2f})")
        return 1

    chunks = [buf[p:p + a.span] for p, _ in kept if p + a.span <= len(buf)]
    print(f"merging {len(chunks)} copies of {a.span} B ...")
    for k in range(2, len(chunks) + 1):
        merged = and_merge(chunks[:k])
        print(f"  {k} copies -> printable {score(merged):.1%}")
    merged = and_merge(chunks)
    text = merged.decode("ascii", "replace")
    print("\n" + "=" * 78)
    print(text)
    print("=" * 78)
    out = a.log + ".recovered.txt"
    open(out, "w", encoding="utf-8", errors="replace").write(text)
    print(f"saved -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
