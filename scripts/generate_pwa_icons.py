"""Render the install icons in frontend/static from the Menagerist mark.

    poe generate-pwa-icons

The PNGs are committed, so a build never needs this; run it when the mark changes.
It reads the shapes in frontend/static/menagerist-icon.svg (a rounded tile, a
polyline and a dot at each vertex) and draws them with Pillow, which the backend
already depends on, at eight times the size before shrinking for smooth edges. It
handles only those shapes, and fails if the SVG gains any other.
"""

import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw

STATIC = Path(__file__).resolve().parent.parent / "frontend" / "static"
SVG = STATIC / "menagerist-icon.svg"
SUPERSAMPLE = 8

# "any" icons keep the rounded tile on a transparent background. The maskable icon
# and the iOS icon are full-bleed squares, since the platform applies its own mask
# and rounding; the mark sits well inside the 80% safe zone a maskable icon must
# keep clear.
ICONS = [
    ("icon-192.png", 192, True),
    ("icon-512.png", 512, True),
    ("icon-maskable-512.png", 512, False),
    ("apple-touch-icon.png", 180, False),
]


def render(svg: ET.Element, size: int, *, rounded: bool) -> Image.Image:
    """Draw the SVG's shapes at `size` pixels square."""
    view = [float(n) for n in svg.attrib["viewBox"].split()]
    big = size * SUPERSAMPLE
    unit = big / view[2]
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    for shape in svg:
        kind = shape.tag.rpartition("}")[2]
        attr = shape.attrib
        if kind == "rect":
            radius = float(attr["rx"]) * unit if rounded else 0
            draw.rounded_rectangle(
                (0, 0, big - 1, big - 1), radius=radius, fill=attr["fill"]
            )
        elif kind == "polyline":
            points = [
                tuple(float(n) * unit for n in pair.split(","))
                for pair in attr["points"].split()
            ]
            colour = ImageColor.getrgb(attr["stroke"])
            width = round(float(attr["stroke-width"]) * unit)
            draw.line(points, fill=colour, width=width)
        elif kind == "circle":
            x, y, r = (float(attr[k]) * unit for k in ("cx", "cy", "r"))
            draw.ellipse((x - r, y - r, x + r, y + r), fill=attr["fill"])
        else:
            raise ValueError(f"menagerist-icon.svg has an unsupported <{kind}>")

    return image.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    """Write every icon."""
    svg = ET.parse(SVG).getroot()
    for name, size, rounded in ICONS:
        render(svg, size, rounded=rounded).save(STATIC / name)
        print(f"{name} {size}x{size}")


if __name__ == "__main__":
    main()
