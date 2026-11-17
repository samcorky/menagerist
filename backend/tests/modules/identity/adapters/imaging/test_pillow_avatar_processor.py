import io

import pytest
from PIL import Image

from app.modules.identity.adapters.imaging import pillow_avatar_processor
from app.modules.identity.adapters.imaging.pillow_avatar_processor import (
    PillowAvatarProcessor,
)
from app.modules.identity.domain.avatar import AVATAR_SIZES, CropSquare
from app.modules.identity.domain.errors import InvalidAvatarError

RED = (255, 0, 0)
BLUE = (0, 0, 255)


def _encode(image: Image.Image, fmt: str, **params: object) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format=fmt, **params)
    return buffer.getvalue()


def _halves(width: int = 200, height: int = 100) -> Image.Image:
    """Left half red, right half blue."""
    image = Image.new("RGB", (width, height), RED)
    image.paste(BLUE, (width // 2, 0, width, height))
    return image


def _open(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    image.load()
    return image


def _mostly(image: Image.Image, colour: tuple[int, int, int]) -> bool:
    r, g, b = image.convert("RGB").resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))  # type: ignore[misc]
    return all(abs(a - c) < 60 for a, c in zip((r, g, b), colour, strict=True))


async def test_outputs_each_size_square_webp() -> None:
    """Every stored size is a square WebP."""
    result = await PillowAvatarProcessor().process(_encode(_halves(), "PNG"), crop=None)
    assert set(result.images) == set(AVATAR_SIZES)
    for size, data in result.images.items():
        image = _open(data)
        assert (image.format, image.size) == ("WEBP", (size, size))


async def test_strips_metadata() -> None:
    """Camera metadata such as the make and location never reaches the output."""
    image = _halves()
    exif = image.getexif()
    exif[0x010F] = "Camera Maker"
    exif[0x8825] = {1: "N"}
    data = _encode(image, "JPEG", exif=exif.tobytes())

    result = await PillowAvatarProcessor().process(data, crop=None)

    for out in result.images.values():
        opened = _open(out)
        assert "exif" not in opened.info
        assert len(opened.getexif()) == 0


async def test_crop_uses_orientation_corrected_coordinates() -> None:
    """A crop names pixels of the picture as shown, after EXIF rotation."""
    image = _halves()
    exif = image.getexif()
    exif[0x0112] = 6  # Shown rotated 90° clockwise: 100 wide, red on top.
    data = _encode(image, "JPEG", exif=exif.tobytes(), quality=95)

    result = await PillowAvatarProcessor().process(
        data, crop=CropSquare(x=0, y=0, size=100)
    )

    assert _mostly(_open(result.images[256]), RED)


async def test_no_crop_takes_centre_square() -> None:
    """Without a crop, the largest centred square is kept."""
    image = Image.new("RGB", (300, 100), BLUE)
    image.paste(RED, (100, 0, 200, 100))
    result = await PillowAvatarProcessor().process(_encode(image, "PNG"), crop=None)
    assert _mostly(_open(result.images[64]), RED)


async def test_crop_clamped_to_bounds() -> None:
    """A crop running off the right edge is moved back inside the picture."""
    result = await PillowAvatarProcessor().process(
        _encode(_halves(), "PNG"), crop=CropSquare(x=150, y=0, size=100)
    )
    assert _mostly(_open(result.images[64]), BLUE)


async def test_oversized_crop_shrinks_to_fit() -> None:
    """A crop larger than the picture keeps the largest square that fits."""
    result = await PillowAvatarProcessor().process(
        _encode(_halves(), "PNG"), crop=CropSquare(x=0, y=0, size=1000)
    )
    assert _open(result.images[256]).size == (256, 256)


async def test_crop_outside_image_is_invalid() -> None:
    """A crop that starts beyond the picture cannot be used."""
    with pytest.raises(InvalidAvatarError):
        await PillowAvatarProcessor().process(
            _encode(_halves(), "PNG"), crop=CropSquare(x=500, y=0, size=100)
        )


async def test_gif_uses_first_frame() -> None:
    """An animated GIF is stored as its first frame."""
    frames = [Image.new("RGB", (50, 50), RED), Image.new("RGB", (50, 50), BLUE)]
    buffer = io.BytesIO()
    frames[0].save(buffer, format="GIF", save_all=True, append_images=frames[1:])
    result = await PillowAvatarProcessor().process(buffer.getvalue(), crop=None)
    out = _open(result.images[64])
    assert not getattr(out, "is_animated", False)
    assert _mostly(out, RED)


async def test_png_alpha_kept() -> None:
    """A transparent picture stays transparent."""
    image = Image.new("RGBA", (50, 50), (255, 0, 0, 0))
    result = await PillowAvatarProcessor().process(_encode(image, "PNG"), crop=None)
    assert _open(result.images[64]).mode == "RGBA"


@pytest.mark.parametrize(
    "data",
    [
        b"hello",
        b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>',
    ],
    ids=["text", "svg"],
)
async def test_rejects_non_image(data: bytes) -> None:
    """Text and SVG are not accepted as pictures."""
    with pytest.raises(InvalidAvatarError):
        await PillowAvatarProcessor().process(data, crop=None)


async def test_rejects_other_raster_formats() -> None:
    """Formats outside JPEG, PNG, WebP and GIF are refused."""
    with pytest.raises(InvalidAvatarError):
        await PillowAvatarProcessor().process(_encode(_halves(), "BMP"), crop=None)


async def test_rejects_too_many_pixels(monkeypatch: pytest.MonkeyPatch) -> None:
    """A picture over the pixel limit is refused, not decoded."""
    monkeypatch.setattr(pillow_avatar_processor, "MAX_PIXELS", 100)
    with pytest.raises(InvalidAvatarError):
        await PillowAvatarProcessor().process(_encode(_halves(), "PNG"), crop=None)


async def test_rejects_truncated_image() -> None:
    """A file that opens but cannot be read to the end is refused."""
    data = _encode(_halves(), "PNG")
    with pytest.raises(InvalidAvatarError):
        await PillowAvatarProcessor().process(data[: len(data) // 2], crop=None)


async def test_version_stable_for_same_input() -> None:
    """The same picture always gets the same version."""
    data = _encode(_halves(), "PNG")
    first = await PillowAvatarProcessor().process(data, crop=None)
    second = await PillowAvatarProcessor().process(data, crop=None)
    assert first.version == second.version
    assert len(first.version) == 16
    assert all(c in "0123456789abcdef" for c in first.version)


async def test_version_changes_with_content() -> None:
    """A different picture gets a different version."""
    one = await PillowAvatarProcessor().process(_encode(_halves(), "PNG"), crop=None)
    other = await PillowAvatarProcessor().process(
        _encode(Image.new("RGB", (50, 50), BLUE), "PNG"), crop=None
    )
    assert one.version != other.version


def _phone_photo(orientation: int | None = None) -> bytes:
    """A 12 MP-sized JPEG (4032x3024), left half red and right half blue."""
    image = _halves(4032, 3024)
    if orientation is None:
        return _encode(image, "JPEG", quality=90)
    exif = image.getexif()
    exif[0x0112] = orientation
    return _encode(image, "JPEG", quality=90, exif=exif.tobytes())


async def test_crop_on_a_phone_sized_jpeg_uses_full_resolution_pixels() -> None:
    """A crop near the far edge of a large JPEG is the region chosen, not refused."""
    result = await PillowAvatarProcessor().process(
        _phone_photo(), crop=CropSquare(x=2500, y=0, size=1500)
    )
    assert _mostly(_open(result.images[256]), BLUE)


async def test_crop_on_a_rotated_phone_sized_jpeg() -> None:
    """Shown rotated (3024 wide, red on top), a bottom crop is all blue."""
    result = await PillowAvatarProcessor().process(
        _phone_photo(orientation=6), crop=CropSquare(x=0, y=2500, size=1500)
    )
    assert _mostly(_open(result.images[256]), BLUE)


async def test_unreadable_orientation_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Corrupt EXIF that breaks rotation keeps the picture as stored, not a 500."""
    from PIL import ImageOps

    def broken(_image: Image.Image) -> Image.Image:
        raise SyntaxError("bad EXIF")

    monkeypatch.setattr(ImageOps, "exif_transpose", broken)
    result = await PillowAvatarProcessor().process(_encode(_halves(), "PNG"), crop=None)
    assert _open(result.images[64]).size == (64, 64)
