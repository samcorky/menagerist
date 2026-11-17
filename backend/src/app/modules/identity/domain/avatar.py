from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.modules.identity.domain.errors import InvalidAvatarError

# The square sizes, in pixels, a picture is stored and served at.
AVATAR_SIZES: tuple[int, ...] = (64, 128, 256)
MAX_AVATAR_BYTES = 5 * 1024 * 1024


class AvatarSource(StrEnum):
    """Where an account's picture came from."""

    UPLOAD = "upload"
    CAT = "cat"
    DRAWN = "drawn"


@dataclass(frozen=True, kw_only=True)
class Avatar:
    """An account's picture; `version` changes whenever the picture does."""

    version: str
    source: AvatarSource
    updated_at: datetime


@dataclass(frozen=True, kw_only=True)
class CropSquare:
    """The square to keep, in pixels of the orientation-corrected image."""

    x: int
    y: int
    size: int

    def __post_init__(self) -> None:
        """Refuse a crop that starts outside the image or covers nothing.

        Raises:
            InvalidAvatarError: If `x` or `y` is negative or `size` is below 1.
        """
        if self.x < 0 or self.y < 0 or self.size < 1:
            raise InvalidAvatarError(
                "A crop must start inside the picture and cover at least one pixel."
            )
