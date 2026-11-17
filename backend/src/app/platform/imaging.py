"""Opening untrusted image bytes without letting them exhaust memory.

Shared by every module that decodes an upload, so the decompression-bomb guard is
written once. Callers map the two errors onto their own domain failures.
"""

import io
import warnings

from PIL import Image, UnidentifiedImageError

from app.shared_kernel.errors import MenageristError


class UndecodableImageError(MenageristError):
    """The bytes are not an image Pillow can open."""


class ImageTooManyPixelsError(MenageristError):
    """The image has more pixels than can be decoded safely."""


def open_image_safely(
    data: bytes, *, max_pixels: int, max_jpeg_pixels: int
) -> Image.Image:
    """Open `data` lazily, refusing images over the pixel limits.

    A JPEG gets its own, usually larger, limit because callers can decode it at a
    fraction of its size with `Image.draft`. The image is opened, not decoded, so a
    truncated file can still fail later when its pixels are read.

    Raises:
        UndecodableImageError: If Pillow cannot identify the bytes.
        ImageTooManyPixelsError: If the image is over its limit, or Pillow's own
            decompression-bomb check trips.
    """
    # Pillow's own check, at open time, uses the larger limit; the per-format limit
    # is applied below. It warns above this and raises above twice it.
    Image.MAX_IMAGE_PIXELS = max(max_pixels, max_jpeg_pixels)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(data))
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise ImageTooManyPixelsError("That image has too many pixels.") from error
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise UndecodableImageError("That file is not a readable image.") from error
    limit = max_jpeg_pixels if image.format == "JPEG" else max_pixels
    if image.width * image.height > limit:
        raise ImageTooManyPixelsError("That image has too many pixels.")
    return image
