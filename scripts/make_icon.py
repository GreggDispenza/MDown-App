#!/usr/bin/env python3
"""Generate the app launcher icon at assets/icon.png (1024x1024).

flet's `flet build` picks up assets/icon.png and derives every Android
launcher density (and the adaptive-icon foreground) from it. Keeping the
generator in-tree makes the icon reproducible rather than an opaque binary:
re-run `python scripts/make_icon.py` to regenerate.

Design: an indigo tile with a white "M" and a down-chevron — "Markdown,
converted down". The glyph sits inside the adaptive-icon safe zone (the
centre ~66%) so Android's circular/rounded masks never clip it. The tile is
full-bleed so the same PNG also works as the legacy square icon; pass the
matching --android-adaptive-icon-background to `flet build` (see build.yml).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SIZE = 1024
BG = (79, 70, 229, 255)      # indigo-600, matches adaptive-icon background
FG = (255, 255, 255, 255)
OUT = Path(__file__).resolve().parent.parent / "assets" / "icon.png"


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    # No bundled TTF is guaranteed on every runner; Pillow's scalable default
    # (Pillow >= 10) is enough for a clean monogram.
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # very old Pillow: fixed-size bitmap default
        return ImageFont.load_default()


def build() -> None:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Full-bleed rounded tile (legacy icon); adaptive mask crops the corners.
    draw.rounded_rectangle([0, 0, SIZE - 1, SIZE - 1], radius=180, fill=BG)

    # Centered "M" monogram, kept within the adaptive safe zone.
    font = _font(560)
    tb = draw.textbbox((0, 0), "M", font=font)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    draw.text(
        ((SIZE - tw) / 2 - tb[0], SIZE * 0.40 - th / 2 - tb[1]),
        "M",
        font=font,
        fill=FG,
    )

    # Down-chevron beneath the M: the "convert to Markdown / down" cue.
    cx, cy = SIZE / 2, SIZE * 0.72
    w, h, t = 190, 92, 46
    draw.line(
        [(cx - w / 2, cy - h / 2), (cx, cy + h / 2), (cx + w / 2, cy - h / 2)],
        fill=FG,
        width=t,
        joint="curve",
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT)
    print(f"wrote {OUT} ({SIZE}x{SIZE})")


if __name__ == "__main__":
    build()
