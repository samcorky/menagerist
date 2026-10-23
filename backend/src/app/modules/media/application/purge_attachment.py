import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.media.ports.unit_of_work import MediaUnitOfWork
from app.shared_kernel.access import Access, System
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.modules.media.ports.media_storage import MediaStoragePort
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class PurgeAttachmentCommand:
    """Request to hard-delete an attachment and the asset only it used."""

    attachment_id: uuid.UUID


class PurgeAttachment(CommandHandler[MediaUnitOfWork, PurgeAttachmentCommand, None]):
    """Hard-delete an attachment, and its asset unless another attachment uses it.

    The stored file goes only after the transaction commits. An unknown id is
    already gone, so a repeat is a no-op.
    """

    access: ClassVar[Access] = System()

    def __init__(
        self, uow: MediaUnitOfWork, guard: AccessGuard, storage: MediaStoragePort
    ) -> None:
        super().__init__(uow, guard)
        self._storage = storage

    async def _handle(self, command: PurgeAttachmentCommand, actor: Actor) -> None:
        """Delete the attachment and any asset left unused, then its file."""
        # all-users: system clean-up
        scope = ContentFilter.everyone()
        async with self._uow as repos:
            attachment = await repos.attachments.get(command.attachment_id, scope=scope)
            if attachment is None:
                return
            asset = await repos.assets.get(attachment.asset_id, scope=scope)
            await repos.attachments.delete(attachment.id)
            remaining = [
                a
                for a in await repos.attachments.list_for_asset(
                    attachment.asset_id, scope=scope
                )
                if a.id != attachment.id
            ]
            drop = asset is not None and not remaining
            if drop:
                await repos.assets.delete(attachment.asset_id)
            await self._uow.commit()
        if asset is not None and drop:
            await self._storage.delete(asset.id, asset.status)
        logger.info("attachment purged", attachment_id=command.attachment_id)
