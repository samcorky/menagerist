from app.modules.media.ports.image_processor import ImageProcessorPort, ThumbnailResult


class InMemoryImageProcessor:
    """In-memory image processor test double for unit tests."""

    def __init__(
        self,
        *,
        generate_result: bool = True,
        fake_thumbnail_bytes: bytes = b"fake-webp-thumbnail",
    ) -> None:
        self._generate_result = generate_result
        self._fake_thumbnail_bytes = fake_thumbnail_bytes

    def generate_thumbnail(
        self, data: bytes, *, max_dimension: int = 320
    ) -> ThumbnailResult | None:
        """Return a synthetic thumbnail or None if decoding should simulate failure."""
        if not self._generate_result or not data:
            return None
        return ThumbnailResult(
            data=self._fake_thumbnail_bytes,
            width=min(max_dimension, 320),
            height=min(max_dimension, 320),
        )


# Verify port protocol conformance at module load
_: type[ImageProcessorPort] = InMemoryImageProcessor
