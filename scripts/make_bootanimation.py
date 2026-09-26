#!/usr/bin/env python3
"""Generate a Google-TV-style bootanimation.zip: black background, wordmark fade-in, looping colour bar.

Usage: make_bootanimation.py OUT.zip [--font PATH] [--text "Google TV"]
"""
import argparse
import io
import os
import zipfile

from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1920, 1080, 30
INTRO_FRAMES, LOOP_FRAMES = 30, 60
FONT_SIZE = 140
COLORS = [(66, 133, 244), (234, 67, 53), (251, 188, 4), (52, 168, 83)]  # blue, red, yellow, green
FALLBACK_FONTS = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def load_font(path):
    for p in ([path] if path else []) + FALLBACK_FONTS:
        if p and os.path.exists(p):
            return ImageFont.truetype(p, FONT_SIZE)
    return ImageFont.load_default()


def seg_alpha(phase, i):
    """Brightness of colour segment i for loop phase in [0,1): a highlight travels left→right."""
    dist = ((phase * 4 - i + 2) % 4) - 2
    return int(255 * (0.35 + 0.65 * max(0.0, 1 - abs(dist))))


def frame(text, font, alpha, phase):
    img = Image.new("RGB", (W, H), "black")
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    l, t, r, b = d.textbbox((0, 0), text, font=font)
    tw, th = r - l, b - t
    d.text(((W - tw) // 2 - l, (H - th) // 2 - t - 40), text, font=font, fill=(255, 255, 255, alpha))
    if phase is not None:
        seg, y, hgt = 120, H // 2 + 90, 6
        x0 = (W - seg * 4) // 2
        for i, c in enumerate(COLORS):
            d.rectangle([x0 + i * seg, y, x0 + (i + 1) * seg - 8, y + hgt], fill=c + (seg_alpha(phase, i),))
    img.paste(layer, (0, 0), layer)
    return img


def png_bytes(img):
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--font")
    ap.add_argument("--text", default="Google TV")
    a = ap.parse_args()
    font = load_font(a.font)
    with zipfile.ZipFile(a.out, "w", zipfile.ZIP_STORED) as z:
        z.writestr("desc.txt", f"{W} {H} {FPS}\np 1 0 part0\np 0 0 part1\n")
        for i in range(INTRO_FRAMES):
            z.writestr(f"part0/{i:04d}.png", png_bytes(frame(a.text, font, 255 * i // (INTRO_FRAMES - 1), None)))
        for i in range(LOOP_FRAMES):
            z.writestr(f"part1/{i:04d}.png", png_bytes(frame(a.text, font, 255, i / LOOP_FRAMES)))
    print(f"wrote {a.out} ({os.path.getsize(a.out)} bytes)")


if __name__ == "__main__":
    main()
