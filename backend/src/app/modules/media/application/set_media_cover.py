import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.modules.media.domain.errors import (
    MediaAssetNotFoundError,
    MediaAttachmentNotFoundError,
    UnsupportedMediaTypeError,
)
from app.modules.media.domain.media_attachment import AttachmentTarget, MediaAttachment
from app.modules.media.ports.unit_of_work import MediaUnitOfWork
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class SetMediaCoverCommand:
    """Mark an already-attached asset as the target's cover image."""

    asset_id: uuid.UUID
    target_type: AttachmentTarget
    target_id: uuid.UUID


class SetMediaCover(
    CommandHandler[MediaUnitOfWork, SetMediaCoverCommand, MediaAttachment]
):
    """Atomically move the cover flag to a different attachment of the same target.

    Only one attachment per target may hold ``attribute_key='cover'`` at a
    time. Any existing cover holder has its flag cleared (not detached) in
    the same transaction as the new cover is set.
    """

    async def handle(
        self, command: SetMediaCoverCommand, actor: Actor
    ) -> MediaAttachment:
        """Set `asset_id`'s attachment as cover, clearing any previous cover."""
        async with self._uow as repos:
            asset = await repos.assets.get(command.asset_id)
            if asset is None:
                msg = f"Media asset {command.asset_id} not found"
                raise MediaAssetNotFoundError(msg)
            if not asset.content_type.startswith("image/"):
                raise UnsupportedMediaTypeError(
                    f"{asset.content_type!r} cannot be used as a cover"
                )

            candidates = await repos.attachments.list_for_target(
                command.target_type, command.target_id
            )

            target_attachment: MediaAttachment | None = None
            for candidate in candidates:
                if candidate.asset_id == command.asset_id:
                    target_attachment = candidate
                elif candidate.attribute_key is not None:
                    candidate.clear_attribute_key()
                    await repos.attachments.update(candidate)

            if target_attachment is None:
                msg = f"{command.target_type} attachment not found: {command.asset_id}"
                raise MediaAttachmentNotFoundError(msg)

            target_attachment.mark_as_cover()
            await repos.attachments.update(target_attachment)
            await self._uow.commit()

        logger.info(
            "media cover set",
            asset_id=command.asset_id,
            target_type=command.target_type.value,
            target_id=command.target_id,
        )
        return target_attachment
