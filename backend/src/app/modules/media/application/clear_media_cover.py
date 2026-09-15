import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.modules.media.domain.errors import MediaAttachmentNotFoundError
from app.modules.media.domain.media_attachment import AttachmentKey, AttachmentTarget
from app.modules.media.ports.unit_of_work import MediaUnitOfWork
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class ClearMediaCoverCommand:
    """Clear an attachment's cover flag without detaching it."""

    asset_id: uuid.UUID
    target_type: AttachmentTarget
    target_id: uuid.UUID


class ClearMediaCover(CommandHandler[MediaUnitOfWork, ClearMediaCoverCommand, None]):
    """Clear the cover flag on an attachment, leaving the asset attached."""

    async def handle(self, command: ClearMediaCoverCommand, actor: Actor) -> None:
        """Clear `asset_id`'s cover flag on the given target."""
        async with self._uow as repos:
            candidates = await repos.attachments.list_for_target(
                command.target_type, command.target_id
            )
            attachment = next(
                (
                    a
                    for a in candidates
                    if a.asset_id == command.asset_id
                    and a.attribute_key == AttachmentKey.COVER
                ),
                None,
            )
            if attachment is None:
                msg = f"{command.target_type} attachment not found: {command.asset_id}"
                raise MediaAttachmentNotFoundError(msg)

            attachment.clear_attribute_key()
            await repos.attachments.update(attachment)
            await self._uow.commit()

        logger.info(
            "media cover cleared",
            asset_id=command.asset_id,
            target_type=command.target_type.value,
            target_id=command.target_id,
        )
