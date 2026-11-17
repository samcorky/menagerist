import io

import pytest
from PIL import Image

from app.platform.imaging import (
    ImageTooManyPixelsError,
    UndecodableImageError,
    open_image_safely,
)


def _png(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "red").save(buffer, format="PNG")
    return buffer.getvalue()


def _jpeg(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "red").save(buffer, format="JPEG")
    return buffer.getvalue()


def test_opens_an_image_within_the_limits() -> None:
    """An ordinary image opens with its format and size."""
    image = open_image_safely(_png(20, 10), max_pixels=1000, max_jpeg_pixels=1000)
    assert (image.format, image.size) == ("PNG", (20, 10))


def test_rejects_bytes_that_are_not_an_image() -> None:
    """Anything Pillow cannot identify is undecodable."""
    with pytest.raises(UndecodableImageError):
        open_image_safely(b"hello", max_pixels=1000, max_jpeg_pixels=1000)


def test_rejects_too_many_pixels() -> None:
    """A non-JPEG over `max_pixels` is refused before it is decoded."""
    with pytest.raises(ImageTooManyPixelsError):
        open_image_safely(_png(40, 30), max_pixels=1000, max_jpeg_pixels=10_000)


def test_jpeg_uses_its_own_limit() -> None:
    """A JPEG is measured against `max_jpeg_pixels`, which may be larger."""
    image = open_image_safely(_jpeg(40, 30), max_pixels=1000, max_jpeg_pixels=10_000)
    assert image.format == "JPEG"
    with pytest.raises(ImageTooManyPixelsError):
        open_image_safely(_jpeg(40, 30), max_pixels=1000, max_jpeg_pixels=1000)


def test_pillow_bomb_warning_becomes_too_many_pixels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pillow's own decompression-bomb check is reported the same way."""

    def bomb(_fp: object) -> Image.Image:
        raise Image.DecompressionBombError("bomb")

    monkeypatch.setattr(Image, "open", bomb)
    with pytest.raises(ImageTooManyPixelsError):
        open_image_safely(b"x", max_pixels=1000, max_jpeg_pixels=1000)
