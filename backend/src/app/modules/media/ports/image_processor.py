from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, kw_only=True)
class ThumbnailResult:
    """A generated thumbnail's encoded bytes and pixel dimensions."""

    data: bytes
    width: int
    height: int


class ImageProcessorPort(Protocol):
    """Port for generating a thumbnail from raw image bytes."""

    def generate_thumbnail(
        self, data: bytes, *, max_dimension: int = 320
    ) -> ThumbnailResult | None:
        """Return a downscaled WEBP thumbnail, or None if undecodable."""
        ...
