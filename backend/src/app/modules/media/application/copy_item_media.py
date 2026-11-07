import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.media.application.permissions import MediaPermission
from app.modules.media.domain.errors import AttachTargetNotFoundError
from app.modules.media.domain.media_asset import MediaAsset, MediaStatus
from app.modules.media.domain.media_attachment import (
    AttachmentKey,
    AttachmentTarget,
    MediaAttachment,
)

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.modules.media.ports.attach_target_access import AttachTargetAccess  # noqa: TC001
from app.modules.media.ports.media_storage import MediaStoragePort  # noqa: TC001
from app.modules.media.ports.unit_of_work import MediaUnitOfWork
from app.shared_kernel.access import Access, Content

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class CopyItemMediaCommand:
    """Copy one item's media onto another, for a duplicate.

    `attachments` copies every attachment except the cover; `cover` copies the
    cover and keeps it the target's cover. Both are independent.
    """

    source_id: uuid.UUID
    target_id: uuid.UUID
    attachments: bool
    cover: bool


class CopyItemMedia(CommandHandler[MediaUnitOfWork, CopyItemMediaCommand, int]):
    """Give the target item its own copies of the source item's files.

    Returns how many attachments were added.
    """

    access: ClassVar[Access] = Content(MediaPermission.ITEM_WRITE)

    def __init__(
        self,
        uow: MediaUnitOfWork,
        guard: AccessGuard,
        storage: MediaStoragePort,
        targets: AttachTargetAccess,
    ) -> None:
        super().__init__(uow, guard)
        self._storage = storage
        self._targets = targets

    async def _handle(self, command: CopyItemMediaCommand, actor: Actor) -> int:
        """Copy each chosen attachment's file and attach the copy to the target.

        Every attachment gets an asset of its own, so deleting a photo on one item
        never touches the other. Files are copied before the rows commit; if
        anything fails, the copies made so far are removed again.
        """
        scope = self.scope(actor)
        if not await self._targets.can_attach(
            AttachmentTarget.NODE, command.target_id, scope
        ):
            raise AttachTargetNotFoundError(f"node {command.target_id} not found")
        copied: list[MediaAsset] = []
        try:
            async with self._uow as repos:
                await repos.attachments.lock_target(
                    AttachmentTarget.NODE, command.target_id
                )
                existing = await repos.attachments.list_for_target(
                    AttachmentTarget.NODE, command.source_id, scope=scope
                )
                chosen = [
                    attachment
                    for attachment in existing
                    if (
                        command.cover
                        if attachment.attribute_key is AttachmentKey.COVER
                        else command.attachments
                    )
                ]
                # One copy per source file, even if two attachments use it.
                copies: dict[uuid.UUID, MediaAsset] = {}
                added = 0
                for attachment in chosen:
                    if attachment.asset_id not in copies:
                        source = await repos.assets.get(
                            attachment.asset_id, scope=scope
                        )
                        if source is None or source.status is not MediaStatus.ATTACHED:
                            continue
                        copy = source.duplicate(owner_id=actor.id)
                        await self._storage.copy(source.id, copy.id, source.status)
                        copied.append(copy)
                        await repos.assets.add(copy)
                        copies[attachment.asset_id] = copy
                    await repos.attachments.add(
                        MediaAttachment.for_target(
                            asset_id=copies[attachment.asset_id].id,
                            target_type=AttachmentTarget.NODE,
                            target_id=command.target_id,
                            attribute_key=attachment.attribute_key,
                        )
                    )
                    added += 1
                await self._uow.commit()
        except BaseException:
            for asset in copied:
                await self._storage.delete(asset.id, asset.status)
            raise
        logger.info(
            "media copied",
            source_id=command.source_id,
            target_id=command.target_id,
            files=len(copied),
        )
        return added
