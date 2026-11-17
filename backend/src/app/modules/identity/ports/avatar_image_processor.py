from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.modules.identity.domain.avatar import CropSquare


@dataclass(frozen=True, kw_only=True)
class ProcessedAvatar:
    """A picture ready to store: WebP bytes for every size in `AVATAR_SIZES`.

    `version` is the first 16 hex digits of the SHA-256 of the 256 px image, so it
    changes whenever the picture does.
    """

    version: str
    images: Mapping[int, bytes]


class AvatarImageProcessor(Protocol):
    """Turns an uploaded file into the square pictures an account shows."""

    async def process(self, data: bytes, *, crop: CropSquare | None) -> ProcessedAvatar:
        """Decode, orient, crop to a square and resize `data`.

        `crop` names pixels of the orientation-corrected image and is clamped to it;
        without one, the largest centred square is kept.

        Raises:
            InvalidAvatarError: If `data` is not a JPEG, PNG, WebP or GIF that can
                be decoded safely, or `crop` lies entirely outside the image.
        """
        ...
