import asyncio
import hashlib
import io

import structlog
from PIL import Image, ImageOps, UnidentifiedImageError

from app.modules.identity.domain.avatar import AVATAR_SIZES, CropSquare
from app.modules.identity.domain.errors import InvalidAvatarError
from app.modules.identity.ports.avatar_image_processor import ProcessedAvatar
from app.platform.imaging import (
    ImageTooManyPixelsError,
    UndecodableImageError,
    open_image_safely,
)

logger = structlog.get_logger()

ALLOWED_FORMATS = frozenset({"JPEG", "PNG", "WEBP", "GIF"})
MAX_PIXELS = 40_000_000
# A JPEG is decoded at a fraction of its size (`Image.draft`), so it may be larger.
MAX_JPEG_PIXELS = 300_000_000
# Large enough that the 256 px output is sharp after a tight crop.
_JPEG_DRAFT_SIZE = 1024

_UNUSABLE = "That file can't be used as a picture."


def _square(image: Image.Image, crop: CropSquare | None) -> Image.Image:
    width, height = image.size
    if crop is None:
        side = min(width, height)
        left, top = (width - side) // 2, (height - side) // 2
        return image.crop((left, top, left + side, top + side))
    if crop.x >= width or crop.y >= height:
        raise InvalidAvatarError("That crop lies outside the picture.")
    side = min(crop.size, width, height)
    left = min(crop.x, width - side)
    top = min(crop.y, height - side)
    return image.crop((left, top, left + side, top + side))


def _upright(image: Image.Image) -> Image.Image:
    """Apply the EXIF orientation; unreadable orientation data is ignored."""
    try:
        return ImageOps.exif_transpose(image)
    except Exception:
        logger.info("picture orientation unreadable; keeping it as stored")
        return image


def _scaled(crop: CropSquare | None, factor: float) -> CropSquare | None:
    if crop is None or factor == 1:
        return crop
    return CropSquare(
        x=int(crop.x * factor),
        y=int(crop.y * factor),
        size=max(1, round(crop.size * factor)),
    )


def _webp(image: Image.Image, size: int) -> bytes:
    resized = image.resize((size, size), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    # No `exif` or `icc_profile`: nothing from the original file is carried over.
    resized.save(buffer, format="WEBP", quality=85, method=6)
    return buffer.getvalue()


def _process(data: bytes, crop: CropSquare | None) -> ProcessedAvatar:
    try:
        loaded = open_image_safely(
            data, max_pixels=MAX_PIXELS, max_jpeg_pixels=MAX_JPEG_PIXELS
        )
    except (ImageTooManyPixelsError, UndecodableImageError) as error:
        raise InvalidAvatarError(_UNUSABLE) from error
    if loaded.format not in ALLOWED_FORMATS:
        raise InvalidAvatarError(_UNUSABLE)
    try:
        full_width = loaded.width
        if loaded.format == "JPEG":
            loaded.draft("RGB", (_JPEG_DRAFT_SIZE, _JPEG_DRAFT_SIZE))
        # A crop names full-resolution pixels; `draft` may have shrunk the image.
        crop = _scaled(crop, loaded.width / full_width)
        oriented = _upright(loaded)
        has_alpha = oriented.mode in ("RGBA", "LA", "PA") or (
            oriented.mode == "P" and "transparency" in oriented.info
        )
        converted = oriented.convert("RGBA" if has_alpha else "RGB")
        square = _square(converted, crop)
        images = {size: _webp(square, size) for size in AVATAR_SIZES}
    except (
        Image.DecompressionBombError,
        UnidentifiedImageError,
        OSError,
        ValueError,
    ) as error:
        raise InvalidAvatarError(_UNUSABLE) from error
    version = hashlib.sha256(images[max(AVATAR_SIZES)]).hexdigest()[:16]
    return ProcessedAvatar(version=version, images=images)


class PillowAvatarProcessor:
    """Pillow-backed `AvatarImageProcessor`; decoding runs off the event loop."""

    @staticmethod
    async def process(data: bytes, *, crop: CropSquare | None) -> ProcessedAvatar:
        """Decode, orient, crop to a square and resize `data` to every size.

        Raises:
            InvalidAvatarError: If `data` is not a usable JPEG, PNG, WebP or GIF, or
                `crop` lies entirely outside the image.
        """
        result = await asyncio.to_thread(_process, data, crop)
        logger.debug("picture processed", version=result.version, input_bytes=len(data))
        return result
