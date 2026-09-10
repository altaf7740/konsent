"""Tray icon art, drawn at runtime so there are no asset files to ship."""
from __future__ import annotations

from PIL import Image, ImageDraw

# Menu bar / tray glyph equivalents, by state.
GLYPH = {"off": "◌", "blurred": "○", "clear": "●"}


def make_icon(state: str, size: int = 64, colour=(255, 255, 255, 255)) -> Image.Image:
    """Filled circle = clear, ring = blurred, faint ring = stopped."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    pad = size // 8
    box = (pad, pad, size - pad - 1, size - pad - 1)

    if state == "clear":
        draw.ellipse(box, fill=colour)
    elif state == "blurred":
        draw.ellipse(box, outline=colour, width=max(2, size // 12))
    else:
        faint = (colour[0], colour[1], colour[2], 110)
        draw.ellipse(box, outline=faint, width=max(2, size // 16))
    return image
