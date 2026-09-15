from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid

    from app.modules.media.domain.media_attachment import (
        AttachmentTarget,
        MediaAttachment,
    )


class MediaAttachmentRepository(Protocol):
    """Port for persisting and querying `MediaAttachment` records."""

    async def add(self, attachment: MediaAttachment) -> None:
        """Persist a new attachment."""
        ...

    async def get(self, attachment_id: uuid.UUID) -> MediaAttachment | None:
        """Return an attachment by id, or ``None``."""
        ...

    async def list_for_target(
        self,
        target_type: AttachmentTarget,
        target_id: uuid.UUID,
    ) -> list[MediaAttachment]:
        """Return all attachments for the given target entity."""
        ...

    async def list_for_asset(self, asset_id: uuid.UUID) -> list[MediaAttachment]:
        """Return all attachments for the given asset."""
        ...

    async def update(self, attachment: MediaAttachment) -> None:
        """Persist changes to an existing attachment."""
        ...

    async def delete(self, attachment_id: uuid.UUID) -> None:
        """Remove an attachment by id."""
        ...
