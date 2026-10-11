from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid

    from app.modules.media.domain.media_attachment import (
        AttachmentTarget,
        MediaAttachment,
    )
    from app.shared_kernel.access_scope import AccessScope


class MediaAttachmentRepository(Protocol):
    """Port for persisting and querying `MediaAttachment` records.

    An attachment is seen when its asset is inside the scope.
    """

    async def lock_target(
        self, target_type: AttachmentTarget, target_id: uuid.UUID
    ) -> None:
        """Serialise cover changes for a target until the transaction ends.

        A concurrent caller for the same target waits here, then sees what the
        first committed.
        """
        ...

    async def add(self, attachment: MediaAttachment) -> None:
        """Persist a new attachment."""
        ...

    async def get(
        self, attachment_id: uuid.UUID, *, scope: AccessScope
    ) -> MediaAttachment | None:
        """Return an attachment by id, or ``None`` if missing or unseen."""
        ...

    async def list_for_target(
        self,
        target_type: AttachmentTarget,
        target_id: uuid.UUID,
        *,
        scope: AccessScope,
    ) -> list[MediaAttachment]:
        """Return the attachments on the target whose asset is inside `scope`."""
        ...

    async def list_for_asset(
        self, asset_id: uuid.UUID, *, scope: AccessScope
    ) -> list[MediaAttachment]:
        """Return the attachments of the asset, if the asset is inside `scope`."""
        ...

    async def update(self, attachment: MediaAttachment) -> None:
        """Persist changes to an existing attachment."""
        ...

    async def delete(self, attachment_id: uuid.UUID) -> None:
        """Remove an attachment by id."""
        ...
