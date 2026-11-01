from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid

    from app.modules.media.domain.media_attachment import AttachmentTarget
    from app.shared_kernel.content_filter import ContentFilter


class AttachTargetAccess(Protocol):
    """Answers whether media may be attached to an entity another module owns."""

    async def can_attach(
        self, target_type: AttachmentTarget, target_id: uuid.UUID, scope: ContentFilter
    ) -> bool:
        """Whether the target exists and is visible inside `scope`."""
        ...
