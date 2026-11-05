"""Render the install icons in frontend/static from the Menagerist mark.

    poe generate-pwa-icons

The PNGs are committed, so a build never needs this; run it when the mark changes.
It draws the mark from frontend/static/menagerist-icon.svg (a 64 unit square) with
Pillow, which the backend already depends on, at eight times the size and shrinks it
for smooth edges.
"""

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "frontend" / "static"
INK = (0x1D, 0x1B, 0x18, 255)
WHITE = (255, 255, 255, 255)
POINTS = [(16, 42), (24, 20), (32, 34), (40, 20), (48, 42)]
STROKE = 3
DOT_RADIUS = 3
TILE_RADIUS = 14
SUPERSAMPLE = 8

# "any" icons keep the rounded tile on a transparent background. The maskable icon
# and the iOS icon are full-bleed squares, since the platform applies its own mask and
# rounding; the mark sits well inside the 80% safe zone a maskable icon must keep clear.
ICONS = [
    ("icon-192.png", 192, True),
    ("icon-512.png", 512, True),
    ("icon-maskable-512.png", 512, False),
    ("apple-touch-icon.png", 180, False),
]


def render(size: int, *, rounded: bool) -> Image.Image:
    """Draw the mark on its tile at `size` pixels square."""
    big = size * SUPERSAMPLE
    unit = big / 64
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    radius = TILE_RADIUS * unit if rounded else 0
    draw.rounded_rectangle((0, 0, big - 1, big - 1), radius=radius, fill=INK)

    points = [(x * unit, y * unit) for x, y in POINTS]
    draw.line(points, fill=WHITE, width=round(STROKE * unit))
    # A dot at each vertex also gives the line round caps and joins.
    for x, y in points:
        r = DOT_RADIUS * unit
        draw.ellipse((x - r, y - r, x + r, y + r), fill=WHITE)

    return image.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    """Write every icon."""
    for name, size, rounded in ICONS:
        render(size, rounded=rounded).save(OUT / name)
        print(f"{name} {size}x{size}")


if __name__ == "__main__":
    main()
