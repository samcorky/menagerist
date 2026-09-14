import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from app.shared_kernel.errors import ValidationError
from app.shared_kernel.mixins import Identifiable, Timestamped


class MediaStatus(StrEnum):
    """Lifecycle state of a media asset."""

    STAGED = "staged"
    ATTACHED = "attached"
    ORPHANED = "orphaned"


@dataclass(kw_only=True, eq=False)
class MediaAsset(Identifiable, Timestamped):
    """Binary media asset attached to a target entity."""

    filename: str
    content_type: str
    size: int
    sha256: str
    status: MediaStatus
    has_thumbnail: bool = False
    thumbnail_sha256: str | None = None

    def __post_init__(self) -> None:
        """Validate invariants after construction."""
        if not self.filename.strip():
            raise ValidationError("filename must be provided")

    @classmethod
    def create(
        cls,
        *,
        asset_id: uuid.UUID | None = None,
        filename: str,
        content_type: str,
        size: int,
        sha256: str,
    ) -> MediaAsset:
        """Create a new staged media asset."""
        now = datetime.now(UTC)
        return cls(
            id=asset_id if asset_id is not None else uuid.uuid7(),
            filename=filename,
            content_type=content_type,
            size=size,
            sha256=sha256,
            status=MediaStatus.STAGED,
            created_at=now,
            updated_at=now,
        )

    def promote(self) -> None:
        """Transition from staged to attached."""
        if self.status is not MediaStatus.STAGED:
            raise ValidationError(
                f"cannot promote a {self.status.value!r} asset; must be staged"
            )
        self.status = MediaStatus.ATTACHED
        self.touch()

    def mark_thumbnail_generated(self, *, sha256: str) -> None:
        """Record that a thumbnail has been generated for this asset.

        `sha256` is the hash of the thumbnail's own bytes, not the
        original's — thumbnails are cached under it independently so
        that regenerating one (e.g. a thumbnailing bug fix) changes its
        cache key even though the original file's `sha256` never does.
        """
        self.has_thumbnail = True
        self.thumbnail_sha256 = sha256

    def orphan(self) -> None:
        """Transition from attached to orphaned."""
        if self.status is not MediaStatus.ATTACHED:
            raise ValidationError(
                f"cannot orphan a {self.status.value!r} asset; must be attached"
            )
        self.status = MediaStatus.ORPHANED
        self.touch()
