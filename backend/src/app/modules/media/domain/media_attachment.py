import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from app.shared_kernel.mixins import Identifiable, Timestamped


class AttachmentTarget(StrEnum):
    """Which entity type a media asset is attached to."""

    NODE = "node"
    EDGE = "edge"


class AttachmentKey(StrEnum):
    """Well-known slot labels for a media attachment."""

    COVER = "cover"


@dataclass(kw_only=True, eq=False)
class MediaAttachment(Identifiable, Timestamped):
    """Link between a media asset and a target entity."""

    asset_id: uuid.UUID
    target_type: AttachmentTarget
    target_id: uuid.UUID
    attribute_key: AttachmentKey | None = field(default=None)

    def mark_as_cover(self) -> None:
        """Flag this attachment as the target's cover."""
        self.attribute_key = AttachmentKey.COVER
        self.touch()

    def clear_attribute_key(self) -> None:
        """Clear this attachment's slot label without detaching it."""
        self.attribute_key = None
        self.touch()

    @classmethod
    def for_target(
        cls,
        *,
        asset_id: uuid.UUID,
        target_type: AttachmentTarget,
        target_id: uuid.UUID,
        attribute_key: AttachmentKey | None = None,
    ) -> MediaAttachment:
        """Create an attachment for any target type."""
        now = datetime.now(UTC)
        return cls(
            id=uuid.uuid7(),
            asset_id=asset_id,
            target_type=target_type,
            target_id=target_id,
            attribute_key=attribute_key,
            created_at=now,
            updated_at=now,
        )

    @classmethod
    def for_node(
        cls,
        *,
        asset_id: uuid.UUID,
        node_id: uuid.UUID,
        attribute_key: AttachmentKey | None = None,
    ) -> MediaAttachment:
        """Create an attachment targeting a node."""
        return cls.for_target(
            asset_id=asset_id,
            target_type=AttachmentTarget.NODE,
            target_id=node_id,
            attribute_key=attribute_key,
        )

    @classmethod
    def for_edge(
        cls,
        *,
        asset_id: uuid.UUID,
        edge_id: uuid.UUID,
        attribute_key: AttachmentKey | None = None,
    ) -> MediaAttachment:
        """Create an attachment targeting an edge."""
        return cls.for_target(
            asset_id=asset_id,
            target_type=AttachmentTarget.EDGE,
            target_id=edge_id,
            attribute_key=attribute_key,
        )
