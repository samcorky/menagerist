import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.media.application.permissions import MediaPermission
from app.modules.media.domain.errors import (
    MediaAssetNotFoundError,
    MediaAttachmentNotFoundError,
)
from app.modules.media.domain.media_asset import MediaStatus
from app.modules.media.domain.media_attachment import AttachmentKey, AttachmentTarget
from app.modules.media.ports.unit_of_work import MediaUnitOfWork
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.modules.media.ports.media_storage import MediaStoragePort
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class DetachMediaCommand:
    """Remove an attachment; orphan the asset if it has no remaining attachments."""

    asset_id: uuid.UUID
    target_type: AttachmentTarget
    target_id: uuid.UUID
    attribute_key: AttachmentKey | None = field(default=None)


class DetachMedia(CommandHandler[MediaUnitOfWork, DetachMediaCommand, None]):
    """Remove a media-entity attachment; orphan the asset if now unreferenced.

    After the attachment row is deleted we check whether the asset is still
    linked anywhere.  If not, it is orphaned (DB commit, then storage move via
    ``on_commit``) so the cleanup job can reap it.
    """

    access: ClassVar[Access] = Content(MediaPermission.ITEM_WRITE)

    def __init__(
        self, uow: MediaUnitOfWork, guard: AccessGuard, storage: MediaStoragePort
    ) -> None:
        super().__init__(uow, guard)
        self._storage = storage

    async def _handle(self, command: DetachMediaCommand, actor: Actor) -> None:
        """Delete the attachment; orphan the asset if it becomes unreferenced."""
        async with self._uow as repos:
            scope = self.scope(actor)
            asset = await repos.assets.get(command.asset_id, scope=scope)
            if asset is None:
                msg = f"Media asset {command.asset_id} not found"
                raise MediaAssetNotFoundError(msg)
            self._guard.assert_can_modify(actor, asset.owner_id)
            candidates = await repos.attachments.list_for_target(
                command.target_type, command.target_id, scope=scope
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

            remaining = await repos.attachments.list_for_asset(
                command.asset_id, scope=scope
            )
            # Filter out the row we just deleted (in-memory flush may not have run).
            remaining = [r for r in remaining if r.id != attachment.id]

            if not remaining and asset.status is MediaStatus.ATTACHED:
                asset.orphan()
                await repos.assets.save(asset)
                asset_id = command.asset_id
                self._uow.on_commit(
                    lambda: self._storage.move(
                        asset_id, MediaStatus.ATTACHED, MediaStatus.ORPHANED
                    )
                )

            await self._uow.commit()
        logger.info(
            "media detached",
            asset_id=command.asset_id,
            target_type=command.target_type.value,
            target_id=command.target_id,
        )
