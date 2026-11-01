import io
import unicodedata

import pytest
from PIL import Image

from app.modules.examples.adapters.covers.in_memory_cover_renderer import (
    InMemoryCoverRenderer,
)
from app.modules.examples.adapters.covers.pillow_cover_renderer import (
    PALETTE,
    PillowCoverRenderer,
    _colour_for,
    _glyph_for,
)
from app.modules.examples.domain.pack import COVER_STYLES

SIZES = {
    "sleeve": (512, 512),
    "poster": (400, 600),
    "box": (600, 450),
    "card": (600, 400),
}
NAMES = [
    "Dune",
    "A very long name " * 20,
    "Éclair",
    "straße",
    "中文",
    "\U0001f600 party",
    "café",
]


def _luminance(rgb: tuple[int, int, int]) -> float:
    def channel(v: int) -> float:
        c = v / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def test_palette_has_twelve_colours_with_white_contrast() -> None:
    """Every palette colour reads clearly under a white letter."""
    assert len(set(PALETTE)) == 12
    for colour in PALETTE:
        assert 1.05 / (_luminance(colour) + 0.05) >= 3.0


@pytest.mark.parametrize("style", COVER_STYLES)
def test_same_input_gives_identical_bytes(style: str) -> None:
    """Rendering is deterministic."""
    assert PillowCoverRenderer().render("Dune", style) == PillowCoverRenderer().render(
        "Dune", style
    )


def test_different_names_give_different_bytes() -> None:
    """Different names produce different covers."""
    renderer = PillowCoverRenderer()
    assert renderer.render("Dune", "card") != renderer.render("Emma", "card")


def test_name_is_case_and_form_insensitive_for_colour() -> None:
    """Case and Unicode form do not change the cover."""
    renderer = PillowCoverRenderer()
    assert renderer.render("dune", "box") == renderer.render("Dune", "box")
    nfc = unicodedata.normalize("NFC", "\u00e9clair")
    nfd = unicodedata.normalize("NFD", "\u00e9clair")
    assert nfc != nfd
    assert renderer.render(nfc, "box") == renderer.render(nfd, "box")


def test_colour_is_pinned_to_a_stable_hash() -> None:
    """Fixed names keep fixed colours, so a salted hash() would fail."""
    assert _colour_for("Dune") == PALETTE[5]
    assert _colour_for("Emma") == PALETTE[1]


def _white_bbox(image: Image.Image) -> tuple[int, int, int, int] | None:
    return (
        image.convert("RGB")
        .point(lambda v: 255 if v > 250 else 0)
        .convert("L")
        .getbbox()
    )


@pytest.mark.parametrize("name", ["\u00e9", "\u00df", "\u0130"])
def test_unsupported_letters_draw_the_question_mark_glyph(name: str) -> None:
    """Letters missing from the font draw a '?' glyph of the same extent."""
    renderer = PillowCoverRenderer()
    assert _glyph_for(name) == "?"
    for style in COVER_STYLES:
        # Names with the same colour index are not guaranteed, so compare glyph boxes.
        a = Image.open(io.BytesIO(renderer.render(name, style)))
        b = Image.open(io.BytesIO(renderer.render("?", style)))
        w, h = a.size
        box = (60, 60, w - 60, h - 60)
        box_a = _white_bbox(a.crop(box))
        box_b = _white_bbox(b.crop(box))
        assert box_a is not None
        assert box_b is not None
        # Edge anti-aliasing differs by a pixel across background colours.
        assert all(abs(x - y) <= 1 for x, y in zip(box_a, box_b, strict=True))


@pytest.mark.parametrize("style", COVER_STYLES)
@pytest.mark.parametrize("name", ["Dune", "Mars", "gold", "Queen"])
def test_glyph_is_centred(name: str, style: str) -> None:
    """The glyph's pixel box is centred on the canvas within 2px."""
    image = Image.open(io.BytesIO(PillowCoverRenderer().render(name, style)))
    width, height = image.size
    inner = image.crop((60, 60, width - 60, height - 60))
    box = _white_bbox(inner)
    assert box is not None
    assert abs(60 + (box[0] + box[2]) / 2 - width / 2) <= 2
    assert abs(60 + (box[1] + box[3]) / 2 - height / 2) <= 2


@pytest.mark.parametrize("style", COVER_STYLES)
@pytest.mark.parametrize("name", NAMES)
def test_renders_valid_small_png_of_expected_size(name: str, style: str) -> None:
    """Each style yields a small PNG of its fixed size."""
    data = PillowCoverRenderer().render(name, style)
    image = Image.open(io.BytesIO(data))
    assert image.format == "PNG"
    assert image.size == SIZES[style]
    assert len(data) < 20 * 1024


def test_glyph_is_first_character_upper_cased() -> None:
    """The glyph is the first non-blank character, upper-cased."""
    assert _glyph_for("  dune") == "D"


@pytest.mark.parametrize("name", ["", "   ", "中文", "\U0001f600 party"])
def test_glyph_falls_back_to_question_mark(name: str) -> None:
    """Blank names and unsupported glyphs draw a question mark."""
    assert _glyph_for(name) == "?"


@pytest.mark.parametrize("name", ["Éclair", "straße"])
def test_glyph_for_accents_is_a_single_character(name: str) -> None:
    """Accented and multi-letter upper-casing never yield more than one character."""
    assert len(_glyph_for(name)) == 1


def test_unknown_style_raises() -> None:
    """An unknown style is rejected."""
    with pytest.raises(ValueError, match="style"):
        PillowCoverRenderer().render("Dune", "banner")


@pytest.mark.parametrize("style", COVER_STYLES)
def test_in_memory_renderer_is_valid_deterministic_and_per_input(style: str) -> None:
    """The fake returns a valid PNG that varies per name."""
    renderer = InMemoryCoverRenderer()
    data = renderer.render("Dune", style)
    assert Image.open(io.BytesIO(data)).format == "PNG"
    assert data == renderer.render("Dune", style)
    assert data != renderer.render("Emma", style)


def test_in_memory_renderer_rejects_unknown_style() -> None:
    """The fake rejects unknown styles like the real renderer."""
    with pytest.raises(ValueError, match="style"):
        InMemoryCoverRenderer().render("Dune", "banner")
