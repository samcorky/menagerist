import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.modules.media.domain.errors import MediaAttachmentNotFoundError
from app.modules.media.domain.media_asset import MediaStatus
from app.modules.media.domain.media_attachment import AttachmentTarget
from app.modules.media.ports.unit_of_work import MediaUnitOfWork
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.modules.media.ports.media_storage import MediaStoragePort
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class DetachMediaCommand:
    """Remove an attachment; orphan the asset if it has no remaining attachments."""

    asset_id: uuid.UUID
    target_type: AttachmentTarget
    target_id: uuid.UUID
    attribute_key: str | None = field(default=None)


class DetachMedia(CommandHandler[MediaUnitOfWork, DetachMediaCommand, None]):
    """Remove a media-entity attachment; orphan the asset if now unreferenced.

    After the attachment row is deleted we check whether the asset is still
    linked anywhere.  If not, it is orphaned (DB commit, then storage move)
    so the cleanup job can reap it.
    """

    def __init__(self, uow: MediaUnitOfWork, storage: MediaStoragePort) -> None:
        super().__init__(uow)
        self._storage = storage

    async def handle(self, command: DetachMediaCommand, actor: Actor) -> None:
        """Delete the attachment; orphan the asset if it becomes unreferenced."""
        should_orphan = False

        async with self._uow as repos:
            candidates = await repos.attachments.list_for_target(
                command.target_type, command.target_id
            )
            attachment = next(
                (
                    a
                    for a in candidates
                    if a.asset_id == command.asset_id
                    and a.attribute_key == command.attribute_key
                ),
                None,
            )
            if attachment is None:
                msg = f"{command.target_type} attachment not found: {command.asset_id}"
                raise MediaAttachmentNotFoundError(msg)

            await repos.attachments.delete(attachment.id)

            remaining = await repos.attachments.list_for_asset(command.asset_id)
            # Filter out the row we just deleted (in-memory flush may not have run).
            remaining = [r for r in remaining if r.id != attachment.id]

            if not remaining:
                asset = await repos.assets.get(command.asset_id)
                if asset is not None and asset.status is MediaStatus.ATTACHED:
                    asset.orphan()
                    await repos.assets.save(asset)
                    should_orphan = True

            await self._uow.commit()

        if should_orphan:
            await self._storage.move(
                command.asset_id, MediaStatus.ATTACHED, MediaStatus.ORPHANED
            )
