import io

import structlog
from PIL import Image, ImageOps, UnidentifiedImageError

from app.modules.media.ports.image_processor import ThumbnailResult

logger = structlog.get_logger()


class PillowImageProcessor:
    """Pillow-backed thumbnail generation.

    Tolerant of undecodable input: this is a safety net for corrupt or
    mislabelled files, not the primary gate — thumbnail_eligibility.py's
    content-type check is what should keep non-image bytes from reaching
    this in the first place.
    """

    @staticmethod
    def generate_thumbnail(
        data: bytes, *, max_dimension: int = 320
    ) -> ThumbnailResult | None:
        """Return downscaled WEBP thumbnail or None if data is undecodable."""
        logger.debug(
            "generating thumbnail", max_dimension=max_dimension, input_bytes=len(data)
        )
        try:
            loaded = Image.open(io.BytesIO(data))
            image: Image.Image = ImageOps.exif_transpose(loaded)
            image.thumbnail((max_dimension, max_dimension))
            buffer = io.BytesIO()
            if image.mode in ("RGBA", "LA") or (
                image.mode == "P" and "transparency" in image.info
            ):
                save_image = image.convert("RGBA")
            else:
                save_image = image.convert("RGB")
            save_image.save(buffer, format="WEBP", quality=85, method=6)
        except UnidentifiedImageError, OSError, ValueError:
            return None
        result = ThumbnailResult(
            data=buffer.getvalue(), width=save_image.width, height=save_image.height
        )
        logger.debug(
            "thumbnail generated",
            width=result.width,
            height=result.height,
            size_bytes=len(result.data),
        )
        return result
