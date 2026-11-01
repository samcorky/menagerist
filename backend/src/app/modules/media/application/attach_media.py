import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.media.application.cover_guard import ensure_cover_free
from app.modules.media.application.permissions import MediaPermission
from app.modules.media.domain.errors import (
    AttachTargetNotFoundError,
    MediaAssetNotFoundError,
)
from app.modules.media.domain.media_asset import MediaStatus
from app.modules.media.domain.media_attachment import (
    AttachmentKey,
    AttachmentTarget,
    MediaAttachment,
)
from app.modules.media.ports.unit_of_work import MediaUnitOfWork
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.modules.media.ports.attach_target_access import AttachTargetAccess
    from app.modules.media.ports.attachment_policy import AttachmentPolicyPort
    from app.modules.media.ports.media_storage import MediaStoragePort
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class AttachMediaCommand:
    """Attach an existing (staged or attached) asset to a graph entity."""

    asset_id: uuid.UUID
    target_type: AttachmentTarget
    target_id: uuid.UUID
    attribute_key: AttachmentKey | None = field(default=None)


class AttachMedia(CommandHandler[MediaUnitOfWork, AttachMediaCommand, MediaAttachment]):
    """Link a media asset to a target entity, promoting from staged if needed."""

    access: ClassVar[Access] = Content(MediaPermission.ITEM_WRITE)

    def __init__(
        self,
        uow: MediaUnitOfWork,
        guard: AccessGuard,
        storage: MediaStoragePort,
        attachment_policy: AttachmentPolicyPort,
        targets: AttachTargetAccess,
    ) -> None:
        super().__init__(uow, guard)
        self._storage = storage
        self._attachment_policy = attachment_policy
        self._targets = targets

    async def _handle(
        self, command: AttachMediaCommand, actor: Actor
    ) -> MediaAttachment:
        """Link the asset to the target entity, promoting it from staged if needed."""
        async with self._uow as repos:
            scope = self.scope(actor)
            asset = await repos.assets.get(command.asset_id, scope=scope)
            if asset is None:
                raise MediaAssetNotFoundError(
                    f"Media asset {command.asset_id} not found"
                )
            self._guard.assert_can_modify(actor, asset.owner_id)
            if not await self._targets.can_attach(
                command.target_type, command.target_id, scope
            ):
                raise AttachTargetNotFoundError(
                    f"{command.target_type} {command.target_id} not found"
                )

            await self._attachment_policy.check(command.target_type, asset)
            await ensure_cover_free(
                repos.attachments,
                attribute_key=command.attribute_key,
                target_type=command.target_type,
                target_id=command.target_id,
                scope=scope,
            )

            if asset.status is MediaStatus.STAGED:
                asset.promote()
                await repos.assets.save(asset)
                self._uow.on_commit(
                    lambda: self._storage.move(
                        asset.id, MediaStatus.STAGED, MediaStatus.ATTACHED
                    )
                )

            attachment = MediaAttachment.for_target(
                asset_id=asset.id,
                target_type=command.target_type,
                target_id=command.target_id,
                attribute_key=command.attribute_key,
            )
            await repos.attachments.add(attachment)
            await self._uow.commit()

        logger.info(
            "media attached",
            asset_id=command.asset_id,
            target_type=command.target_type.value,
            target_id=command.target_id,
        )
        return attachment
