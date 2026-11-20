"""Render the install icons, shortcut icons and link-preview image in frontend/static.

    poe generate-pwa-icons

The PNGs are committed, so a build never needs this; run it when the mark changes.
It reads the shapes in frontend/static/menagerist-icon.svg (a rounded tile, a
polyline and a dot at each vertex) and draws them with Pillow, which the backend
already depends on, at eight times the size before shrinking for smooth edges. It
handles only those shapes, and fails if the SVG gains any other.

The launcher shortcut icons are different: they are Lucide glyphs, drawn from the path
data in `@lucide/svelte` and rasterised with resvg (`resvg-py`), since Pillow cannot
draw SVG paths. So `poe sync` must have run, as it must for the share image's font.
"""

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import resvg_py
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

# Launcher shortcut icons: the glyph each shortcut's button uses in the phone tab bar
# (frontend/src/lib/manage-nav.ts), white on the brand tile. A launcher draws the icon
# on its own menu surface, light or dark, so the glyph carries its own background
# rather than relying on either. The tile is full-bleed because the launcher masks it,
# and the glyph fills GLYPH_SHARE of it, inside the safe zone a mask leaves clear.
SHORTCUT_ICON_SIZE = 192
SHORTCUT_ICONS = [
    ("shortcut-add-item.png", "circle-plus"),
    ("shortcut-items.png", "layout-grid"),
    ("shortcut-collections.png", "library"),
]
GLYPH_SHARE = 0.6
LUCIDE_ICONS = STATIC.parent / "node_modules" / "@lucide" / "svelte" / "dist" / "icons"

# The link-preview card. 1200x630 is the size Open Graph and Twitter large cards
# expect (about 1.9:1); app.html names the file and these dimensions.
#
# The lockup uses the header's ingredients (frontend/src/routes/+layout.svelte):
# logo.svg, then the name in Inter semibold with tight tracking (-0.025em), but
# stacked and centred, not side by side. Microsoft Teams shows a compact card and
# centre-crops the image to a squarer thumbnail, so everything must sit inside the
# middle SHARE_SAFE_WIDTH pixels. Sizes below are in em, so SHARE_FONT is the only
# thing that scales it.
SHARE_IMAGE = "share-image.png"
SHARE_SIZE = (1200, 630)
SHARE_NAME = "Menagerist"
SHARE_FONT = 104
SHARE_FONT_WEIGHT = 600
SHARE_MARK_EM = 1.5
SHARE_GAP_EM = 0.25
SHARE_SAFE_WIDTH = 600
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


def lucide_glyph(name: str) -> str:
    """Return the SVG elements of a Lucide icon, read from its `__iconData`."""
    source = (LUCIDE_ICONS / f"{name}.svelte").read_text()
    found = re.search(r"__iconData = (\{.*?\});", source, re.DOTALL)
    assert found, f"no __iconData in {name}.svelte"
    data = json.loads(found.group(1))
    size = data["size"]
    assert size == 24, f"{name} is not on Lucide's 24-unit grid"
    shapes = []
    for tag, attrs in data["node"]:
        spelled = " ".join(f'{key}="{value}"' for key, value in attrs.items())
        shapes.append(f"<{tag} {spelled}/>")
    return "".join(shapes)


def render_shortcut_icon(name: str, tile: str) -> bytes:
    """Draw a Lucide glyph, white on the full-bleed tile, as PNG bytes."""
    size = SHORTCUT_ICON_SIZE
    scale = size * GLYPH_SHARE / 24
    offset = (size - 24 * scale) / 2
    glyph_style = 'fill="none" stroke="#FFFFFF" stroke-width="2"'
    glyph_style += ' stroke-linecap="round" stroke-linejoin="round"'
    svg = "".join(
        [
            '<svg xmlns="http://www.w3.org/2000/svg"',
            f' width="{size}" height="{size}" viewBox="0 0 {size} {size}">',
            f'<rect width="{size}" height="{size}" fill="{tile}"/>',
            f'<g transform="translate({offset} {offset}) scale({scale})"',
            f" {glyph_style}>{lucide_glyph(name)}</g></svg>",
        ]
    )
    return bytes(resvg_py.svg_to_bytes(svg_string=svg, width=size, height=size))


def render_share_image(icon: ET.Element) -> Image.Image:
    """Draw the link-preview card: the mark above the name, centred on the tile."""
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
    mark_ink_height = ink_box[3] - ink_box[1]

    # Where each letter starts. Measuring the text up to a letter keeps the font's
    # kerning; the tracking is added on top, as CSS letter-spacing does.
    starts = [
        font.getlength(SHARE_NAME[:i]) + i * tracking for i in range(len(SHARE_NAME))
    ]
    name_ink_right = starts[-1] + font.getbbox(SHARE_NAME[-1])[2]
    name_ink_left = font.getbbox(SHARE_NAME[0])[0]
    name_width = name_ink_right - name_ink_left
    assert name_width <= SHARE_SAFE_WIDTH, "the name must fit the Teams crop"

    # The name's drawn height is its capitals (no descender in the name), so stack
    # the mark's drawn height, the gap and the cap height, and centre that block.
    width, height = SHARE_SIZE
    cap_top = font.getbbox("M", anchor="ls")[1]  # negative: above the baseline
    cap_height = -cap_top
    block = mark_ink_height + gap + cap_height
    top = round((height - block) / 2)
    mark_x = round((width - box) / 2)
    image.paste(mark, (mark_x, top - ink_box[1]), mark)
    baseline = top + mark_ink_height + gap + cap_height
    text_x = round((width - name_width) / 2) - name_ink_left
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
    tile = next(s for s in svg if s.tag.rpartition("}")[2] == "rect").attrib["fill"]
    for name, glyph in SHORTCUT_ICONS:
        (STATIC / name).write_bytes(render_shortcut_icon(glyph, tile))
        print(f"{name} {SHORTCUT_ICON_SIZE}x{SHORTCUT_ICON_SIZE}")


if __name__ == "__main__":
    main()
