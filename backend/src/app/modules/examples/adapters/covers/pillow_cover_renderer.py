import hashlib
import io
import unicodedata
from functools import cache

from PIL import Image, ImageDraw, ImageFont
from PIL.ImageFont import FreeTypeFont

from app.modules.examples.domain.pack import COVER_STYLES

# Each colour has a contrast ratio of at least 3:1 against white.
PALETTE: tuple[tuple[int, int, int], ...] = (
    (0xB7, 0x1C, 0x1C),
    (0xAD, 0x14, 0x57),
    (0x6A, 0x1B, 0x9A),
    (0x45, 0x27, 0xA0),
    (0x28, 0x35, 0x93),
    (0x15, 0x65, 0xC0),
    (0x00, 0x69, 0x7C),
    (0x00, 0x69, 0x5C),
    (0x2E, 0x7D, 0x32),
    (0x55, 0x6B, 0x2F),
    (0xA3, 0x4A, 0x00),
    (0x4E, 0x34, 0x2E),
)

SIZES: dict[str, tuple[int, int]] = {
    "sleeve": (512, 512),
    "poster": (400, 600),
    "box": (600, 450),
    "card": (600, 400),
}

_WHITE = (255, 255, 255)
_MISSING_PROBE = "\U0010ffff"


def _darken(colour: tuple[int, int, int]) -> tuple[int, int, int]:
    r, g, b = colour
    return (r * 3 // 4, g * 3 // 4, b * 3 // 4)


@cache
def _font(size: int) -> FreeTypeFont:
    font = ImageFont.load_default(size=size)
    assert isinstance(font, FreeTypeFont)
    return font


def _has_glyph(font: FreeTypeFont, char: str) -> bool:
    if not font.getmask(char).getbbox():
        return False
    return bytes(font.getmask(char)) != bytes(font.getmask(_MISSING_PROBE))


def _ink_box(glyph: str, font: FreeTypeFont) -> tuple[int, int, int, int]:
    """Return the glyph's drawn pixel box relative to its `ls` origin."""
    scratch = Image.new("L", (400, 400))
    ImageDraw.Draw(scratch).text((100, 300), glyph, fill=255, font=font, anchor="ls")
    left, top, right, bottom = scratch.getbbox() or (100, 300, 100, 300)
    return left - 100, top - 300, right - 100, bottom - 300


def _glyph_for(name: str) -> str:
    """Return the character to draw: the first of `name`, or `?` if unavailable."""
    stripped = unicodedata.normalize("NFC", name).strip()
    if not stripped:
        return "?"
    char = stripped[0].upper()
    if len(char) != 1 or not _has_glyph(_font(64), char):
        return "?"
    return char


def _colour_for(name: str) -> tuple[int, int, int]:
    folded = unicodedata.normalize("NFC", name).strip().casefold()
    digest = hashlib.sha256(folded.encode()).digest()
    return PALETTE[int.from_bytes(digest[:4], "big") % len(PALETTE)]


class PillowCoverRenderer:
    """Draws flat PNG covers: a coloured field, a style shape and one letter."""

    def render(self, name: str, style: str) -> bytes:
        """Return deterministic PNG bytes for `name` in `style`.

        Raises:
            ValueError: If `style` is not a known cover style.
        """
        if style not in COVER_STYLES:
            raise ValueError(f"unknown cover style '{style}'")
        width, height = SIZES[style]
        colour = _colour_for(name)
        accent = _darken(colour)
        image = Image.new("RGB", (width, height), colour)
        draw = ImageDraw.Draw(image)

        if style == "sleeve":
            margin = width // 8
            draw.ellipse((margin, margin, width - margin, height - margin), fill=accent)
        elif style == "poster":
            draw.rectangle((0, 0, width, height // 6), fill=accent)
        elif style == "box":
            inset = 24
            draw.rectangle(
                (inset, inset, width - inset, height - inset), outline=_WHITE, width=6
            )
        else:
            draw.rectangle((0, height * 5 // 6, width, height), fill=accent)

        font = _font(min(width, height) // 2)
        glyph = _glyph_for(name)
        left, top, right, bottom = _ink_box(glyph, font)
        draw.text(
            (
                round(width / 2 - (left + right) / 2),
                round(height / 2 - (top + bottom) / 2),
            ),
            glyph,
            fill=_WHITE,
            font=font,
            anchor="ls",
        )

        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()
