import io

from PIL import Image, UnidentifiedImageError

from app.modules.media.ports.image_processor import ThumbnailResult


class PillowImageProcessor:
    """Pillow-backed thumbnail generation.

    Tolerant of undecodable input: this is a safety net for corrupt or
    mislabelled files, not the primary gate — thumbnail_eligibility.py's
    content-type check is what should keep non-image bytes from reaching
    this in the first place.
    """

    def generate_thumbnail(
        self, data: bytes, *, max_dimension: int = 320
    ) -> ThumbnailResult | None:
        """Return downscaled WEBP thumbnail or None if data is undecodable."""
        try:
            image = Image.open(io.BytesIO(data))
            image.thumbnail((max_dimension, max_dimension))
            buffer = io.BytesIO()
            if image.mode in ("RGBA", "LA") or (
                image.mode == "P" and "transparency" in image.info
            ):
                save_image = image.convert("RGBA")
            else:
                save_image = image.convert("RGB")
            save_image.save(buffer, format="WEBP", quality=80)
        except UnidentifiedImageError, OSError, ValueError:
            return None
        return ThumbnailResult(
            data=buffer.getvalue(), width=save_image.width, height=save_image.height
        )
