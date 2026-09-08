from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid

    from app.modules.media.domain.media_attachment import (
        AttachmentTarget,
        MediaAttachment,
    )


class InMemoryMediaAttachmentRepository:
    """Dict-backed `MediaAttachmentRepository` for tests — no database required."""

    def __init__(self) -> None:
        self._store: dict[uuid.UUID, MediaAttachment] = {}

    async def add(self, attachment: MediaAttachment) -> None:
        """Store an attachment."""
        self._store[attachment.id] = attachment

    async def get(self, attachment_id: uuid.UUID) -> MediaAttachment | None:
        """Return an attachment by id, or ``None``."""
        return self._store.get(attachment_id)

    async def list_for_target(
        self,
        target_type: AttachmentTarget,
        target_id: uuid.UUID,
    ) -> list[MediaAttachment]:
        """Return all attachments for the given target entity."""
        return [
            a
            for a in self._store.values()
            if a.target_type == target_type and a.target_id == target_id
        ]

    async def list_for_asset(self, asset_id: uuid.UUID) -> list[MediaAttachment]:
        """Return all attachments for the given asset."""
        return [a for a in self._store.values() if a.asset_id == asset_id]

    async def delete(self, attachment_id: uuid.UUID) -> None:
        """Remove an attachment by id (no-op if absent)."""
        self._store.pop(attachment_id, None)
