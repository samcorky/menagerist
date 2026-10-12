import io

import pytest
from PIL import Image

from app.modules.media.adapters.imaging import pillow_processor
from app.modules.media.adapters.imaging.pillow_processor import PillowImageProcessor
from app.modules.media.domain.errors import ImageTooLargeError


def test_pillow_image_processor_generates_webp_thumbnail() -> None:
    """Pillow processor generates a WebP thumbnail preserving RGBA transparency."""
    processor = PillowImageProcessor()

    # Create a 640x480 RGBA image in memory
    img = Image.new("RGBA", (640, 480), color=(255, 0, 0, 128))
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    png_bytes = buffer.getvalue()

    result = processor.generate_thumbnail(png_bytes, max_dimension=320)
    assert result is not None
    assert result.width == 320
    assert result.height == 240
    assert len(result.data) > 0

    # Ensure output is a valid WebP image
    out_img = Image.open(io.BytesIO(result.data))
    assert out_img.format == "WEBP"
    assert out_img.mode == "RGBA"


def test_pillow_image_processor_rgb_image() -> None:
    """Pillow processor downscales RGB images properly."""
    processor = PillowImageProcessor()

    img = Image.new("RGB", (100, 200), color=(0, 255, 0))
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG")
    jpeg_bytes = buffer.getvalue()

    result = processor.generate_thumbnail(jpeg_bytes, max_dimension=320)
    assert result is not None
    assert result.width == 100
    assert result.height == 200

    out_img = Image.open(io.BytesIO(result.data))
    assert out_img.format == "WEBP"


def test_pillow_image_processor_corrects_exif_orientation() -> None:
    """Thumbnail orientation matches visual content, not raw pixel layout."""
    processor = PillowImageProcessor()

    # Create a 200x100 landscape image then embed orientation=6 (rotate 90° CW),
    # which simulates a portrait shot stored sideways - raw pixels are 200x100
    # but the EXIF tag says "display as 100x200".
    img = Image.new("RGB", (200, 100), color=(0, 0, 255))
    buffer = io.BytesIO()
    exif = img.getexif()
    exif[0x0112] = 6  # Orientation tag: 90° CW
    img.save(buffer, format="JPEG", exif=exif.tobytes())

    result = processor.generate_thumbnail(buffer.getvalue(), max_dimension=320)
    assert result is not None
    # After transpose, the image should be portrait (100 wide x 200 tall)
    assert result.width < result.height


def test_pillow_image_processor_returns_none_for_corrupt_data() -> None:
    """Pillow processor returns None gracefully when decoding corrupt image bytes."""
    processor = PillowImageProcessor()
    result = processor.generate_thumbnail(b"corrupt non-image data", max_dimension=320)
    assert result is None


def _png(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("L", (width, height)).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.mark.parametrize("size", [(15, 10), (30, 30)])
def test_pillow_image_processor_refuses_a_decompression_bomb(
    monkeypatch: pytest.MonkeyPatch, size: tuple[int, int]
) -> None:
    """Both Pillow's warning band and its error band become ImageTooLargeError."""
    monkeypatch.setattr(pillow_processor, "MAX_IMAGE_PIXELS", 100)

    with pytest.raises(ImageTooLargeError):
        PillowImageProcessor().generate_thumbnail(_png(*size))


def test_pillow_image_processor_accepts_an_image_within_the_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An image at the limit still gets a thumbnail."""
    monkeypatch.setattr(pillow_processor, "MAX_IMAGE_PIXELS", 100)

    result = PillowImageProcessor().generate_thumbnail(_png(10, 10))

    assert result is not None
