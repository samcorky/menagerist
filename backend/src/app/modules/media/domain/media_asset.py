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
    """A binary file (image, document, etc.) attached to a graph node.

    Lifecycle: staged → attached → orphaned → (hard deleted by cleanup).
    """

    filename: str
    content_type: str
    size: int
    sha256: str
    status: MediaStatus

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
        """Create a new staged media asset.

        `asset_id` lets the caller pre-generate the id (needed when the id must
        be known before the file is written to storage).
        """
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
        """Transition from staged to attached.

        Raises `ValidationError` if the asset is not currently staged.
        """
        if self.status is not MediaStatus.STAGED:
            raise ValidationError(
                f"cannot promote a {self.status.value!r} asset; must be staged"
            )
        self.status = MediaStatus.ATTACHED
        self.touch()

    def orphan(self) -> None:
        """Transition from attached to orphaned.

        Raises `ValidationError` if the asset is not currently attached.
        """
        if self.status is not MediaStatus.ATTACHED:
            raise ValidationError(
                f"cannot orphan a {self.status.value!r} asset; must be attached"
            )
        self.status = MediaStatus.ORPHANED
        self.touch()
