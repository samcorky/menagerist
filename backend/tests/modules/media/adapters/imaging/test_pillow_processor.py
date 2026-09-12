import io

from PIL import Image

from app.modules.media.adapters.imaging.pillow_processor import PillowImageProcessor


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


def test_pillow_image_processor_returns_none_for_corrupt_data() -> None:
    """Pillow processor returns None gracefully when decoding corrupt image bytes."""
    processor = PillowImageProcessor()
    result = processor.generate_thumbnail(b"corrupt non-image data", max_dimension=320)
    assert result is None
