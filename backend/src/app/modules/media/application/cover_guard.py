from typing import TYPE_CHECKING

from app.modules.media.domain.errors import CoverAlreadySetError
from app.modules.media.domain.media_attachment import AttachmentKey

if TYPE_CHECKING:
    import uuid

    from app.modules.media.domain.media_attachment import AttachmentTarget
    from app.modules.media.ports.media_attachment_repository import (
        MediaAttachmentRepository,
    )


async def ensure_cover_free(
    attachments: MediaAttachmentRepository,
    *,
    attribute_key: AttachmentKey | None,
    target_type: AttachmentTarget,
    target_id: uuid.UUID,
) -> None:
    """Raise `CoverAlreadySetError` if a new cover would be a second one."""
    if attribute_key is not AttachmentKey.COVER:
        return
    existing = await attachments.list_for_target(target_type, target_id)
    if any(a.attribute_key is AttachmentKey.COVER for a in existing):
        raise CoverAlreadySetError
