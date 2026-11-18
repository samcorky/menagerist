"""Render the install icons and link-preview image in frontend/static from the mark.

    poe generate-pwa-icons

The PNGs are committed, so a build never needs this; run it when the mark changes.
It reads the shapes in frontend/static/menagerist-icon.svg (a rounded tile, a
polyline and a dot at each vertex) and draws them with Pillow, which the backend
already depends on, at eight times the size before shrinking for smooth edges. It
handles only those shapes, and fails if the SVG gains any other.
"""

import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFont

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

# The link-preview card. 1200x630 is the size Open Graph and Twitter large cards
# expect (about 1.9:1); app.html names the file and these dimensions.
#
# The lockup copies the app's header (frontend/src/routes/+layout.svelte): logo.svg
# in a box 1.5em square, 0.5em gap, then the name in Inter semibold with tight
# tracking (-0.025em), centred on one line. Sizes below are in em, so SHARE_FONT is
# the only thing that scales it.
SHARE_IMAGE = "share-image.png"
SHARE_SIZE = (1200, 630)
SHARE_NAME = "Menagerist"
SHARE_FONT = 144
SHARE_FONT_WEIGHT = 600
SHARE_MARK_EM = 1.5
SHARE_GAP_EM = 0.5
SHARE_TRACKING_EM = -0.025
SHARE_LOGO = STATIC / "logo.svg"
# Inter is the app's body font, read from the variable font file the frontend
# installs, so `poe sync` must have run.
SHARE_FONT_FILE = (
    STATIC.parent
    / "node_modules"
    / "@fontsource-variable"
    / "inter"
    / "files"
    / "inter-latin-wght-normal.woff2"
)


def render(
    svg: ET.Element, size: int, *, rounded: bool, ink: str | None = None
) -> Image.Image:
    """Draw the SVG's shapes at `size` pixels square, in `ink` if given."""
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
            colour = ImageColor.getrgb(ink or attr["stroke"])
            width = round(float(attr["stroke-width"]) * unit)
            draw.line(points, fill=colour, width=width)
        elif kind == "circle":
            x, y, r = (float(attr[k]) * unit for k in ("cx", "cy", "r"))
            draw.ellipse((x - r, y - r, x + r, y + r), fill=ink or attr["fill"])
        else:
            raise ValueError(f"an SVG has an unsupported <{kind}>")

    return image.resize((size, size), Image.Resampling.LANCZOS)


def render_share_image(icon: ET.Element) -> Image.Image:
    """Draw the link-preview card: the app's header lockup on the tile's colour."""
    tile = next(shape for shape in icon if shape.tag.rpartition("}")[2] == "rect")
    image = Image.new("RGB", SHARE_SIZE, tile.attrib["fill"])
    font = ImageFont.truetype(str(SHARE_FONT_FILE), SHARE_FONT)
    font.set_variation_by_axes([SHARE_FONT_WEIGHT])

    box = round(SHARE_FONT * SHARE_MARK_EM)
    gap = round(SHARE_FONT * SHARE_GAP_EM)
    tracking = SHARE_FONT * SHARE_TRACKING_EM
    mark = render(ET.parse(SHARE_LOGO).getroot(), box, rounded=False, ink="#FFFFFF")
    ink_box = mark.getbbox()
    assert ink_box is not None  # the logo draws something
    ink_left = ink_box[0]

    # Where each letter starts. Measuring the text up to a letter keeps the font's
    # kerning; the tracking is added on top, as CSS letter-spacing does.
    starts = [
        font.getlength(SHARE_NAME[:i]) + i * tracking for i in range(len(SHARE_NAME))
    ]
    name_ink_right = starts[-1] + font.getbbox(SHARE_NAME[-1])[2]

    # Centre the visible lockup, from the mark's drawn edge to the last letter.
    width, height = SHARE_SIZE
    visible = (box - ink_left) + gap + name_ink_right
    box_x = round((width - visible) / 2) - ink_left
    text_x = box_x + box + gap

    # The header lines the mark's box up with the text's line box, which runs from
    # the font's ascent to its descent, so both share that line's centre.
    ascent, descent = font.getmetrics()
    centre = height / 2
    baseline = round(centre + (ascent - descent) / 2)
    image.paste(mark, (box_x, round(centre - box / 2)), mark)
    draw = ImageDraw.Draw(image)
    for letter, start in zip(SHARE_NAME, starts, strict=True):
        draw.text(
            (text_x + start, baseline), letter, font=font, fill="#FFFFFF", anchor="ls"
        )
    return image


def main() -> None:
    """Write every icon and the share image."""
    svg = ET.parse(SVG).getroot()
    for name, size, rounded in ICONS:
        render(svg, size, rounded=rounded).save(STATIC / name)
        print(f"{name} {size}x{size}")
    render_share_image(svg).save(STATIC / SHARE_IMAGE, optimize=True)
    print(f"{SHARE_IMAGE} {SHARE_SIZE[0]}x{SHARE_SIZE[1]}")


if __name__ == "__main__":
    main()
