#!/usr/bin/env python3
"""Generate the Google Play store graphic assets under assets/play/.

Play Console requires, at minimum:
  - a 512x512 32-bit PNG app icon (no transparency — Play applies its own
    rounding), and
  - a 1024x500 feature graphic.

Both are brand assets derived from the same MDown glyph as the launcher icon
(scripts/make_icon.py), so the store presence matches the installed app.
Regenerate with `python scripts/make_store_assets.py`. Phone screenshots are
NOT generated here — capture those from the running app (see
docs/play-store-listing.md).
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))  # allow same-dir import
from make_icon import BG, FG, _font, render_tile  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "play"
INDIGO_DARK = (67, 56, 202, 255)   # indigo-700, for the feature-graphic wash


def store_icon() -> None:
    # Full opaque square (radius 0): Play masks corners itself and rejects
    # transparency in the hi-res icon.
    path = OUT_DIR / "icon-512.png"
    render_tile(512, radius=0).convert("RGB").save(path)
    print(f"wrote {path} (512x512)")


def feature_graphic() -> None:
    w, h = 1024, 500
    img = Image.new("RGB", (w, h), BG[:3])
    draw = ImageDraw.Draw(img)
    # Subtle diagonal wash for depth.
    for x in range(w):
        blend = x / w
        r = int(BG[0] + (INDIGO_DARK[0] - BG[0]) * blend)
        g = int(BG[1] + (INDIGO_DARK[1] - BG[1]) * blend)
        b = int(BG[2] + (INDIGO_DARK[2] - BG[2]) * blend)
        draw.line([(x, 0), (x, h)], fill=(r, g, b))

    tile = render_tile(300, radius=56)
    img.paste(tile, (90, (h - 300) // 2), tile)

    title_font = _font(150)
    tag_font = _font(46)
    draw.text((440, 150), "MDown", font=title_font, fill=FG)
    draw.text((446, 300), "Documents to Markdown", font=tag_font, fill=(224, 222, 255))

    path = OUT_DIR / "feature-graphic-1024x500.png"
    img.save(path)
    print(f"wrote {path} (1024x500)")


def build() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    store_icon()
    feature_graphic()


if __name__ == "__main__":
    build()
