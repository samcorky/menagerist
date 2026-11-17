import io

import structlog
from PIL import Image, ImageOps, UnidentifiedImageError

from app.modules.media.domain.errors import ImageTooLargeError
from app.modules.media.ports.image_processor import ThumbnailResult
from app.platform.imaging import (
    ImageTooManyPixelsError,
    UndecodableImageError,
    open_image_safely,
)

logger = structlog.get_logger()

# Decoding needs several bytes per pixel and a few copies, so cap the raster.
MAX_IMAGE_PIXELS = 40_000_000
# A JPEG is decoded at a fraction of its size for a thumbnail (`Image.draft`), so
# it can be far larger: phone and camera photos stay well under this.
MAX_JPEG_PIXELS = 300_000_000


class PillowImageProcessor:
    """Pillow-backed thumbnail generation.

    Tolerant of undecodable input: this is a safety net for corrupt or
    mislabelled files, not the primary gate - thumbnail_eligibility.py's
    content-type check is what should keep non-image bytes from reaching
    this in the first place.
    """

    @staticmethod
    def generate_thumbnail(
        data: bytes, *, max_dimension: int = 320
    ) -> ThumbnailResult | None:
        """Return downscaled WEBP thumbnail or None if data is undecodable.

        Raises:
            ImageTooLargeError: If the image exceeds `MAX_IMAGE_PIXELS`, or
                `MAX_JPEG_PIXELS` for a JPEG (a decompression bomb).
        """
        logger.debug(
            "generating thumbnail", max_dimension=max_dimension, input_bytes=len(data)
        )
        try:
            loaded = open_image_safely(
                data, max_pixels=MAX_IMAGE_PIXELS, max_jpeg_pixels=MAX_JPEG_PIXELS
            )
        except ImageTooManyPixelsError as error:
            raise ImageTooLargeError("That image has too many pixels.") from error
        except UndecodableImageError:
            return None
        try:
            if loaded.format == "JPEG":
                loaded.draft(loaded.mode, (max_dimension, max_dimension))
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
        except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
            raise ImageTooLargeError("That image has too many pixels.") from error
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
