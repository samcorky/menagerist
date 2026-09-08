import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.modules.media.domain.errors import MediaAssetNotFoundError
from app.modules.media.domain.media_asset import MediaStatus
from app.modules.media.domain.media_attachment import AttachmentTarget, MediaAttachment
from app.modules.media.ports.unit_of_work import MediaUnitOfWork
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.modules.media.ports.attachment_policy import AttachmentPolicyPort
    from app.modules.media.ports.media_storage import MediaStoragePort
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class AttachMediaCommand:
    """Attach an existing (staged or attached) asset to a graph entity."""

    asset_id: uuid.UUID
    target_type: AttachmentTarget
    target_id: uuid.UUID
    attribute_key: str | None = field(default=None)


class AttachMedia(CommandHandler[MediaUnitOfWork, AttachMediaCommand, MediaAttachment]):
    """Link a media asset to a graph entity, promoting it from staged if needed.

    DB commit comes before the storage move so the DB is always authoritative
    about asset state (same ordering as PromoteMedia).
    """

    def __init__(
        self,
        uow: MediaUnitOfWork,
        storage: MediaStoragePort,
        policy: AttachmentPolicyPort,
    ) -> None:
        super().__init__(uow)
        self._storage = storage
        self._policy = policy

    async def handle(
        self, command: AttachMediaCommand, actor: Actor
    ) -> MediaAttachment:
        """Link the asset to the target entity, promoting it from staged if needed."""
        was_staged = False

        async with self._uow as repos:
            asset = await repos.assets.get(command.asset_id)
            if asset is None:
                raise MediaAssetNotFoundError(
                    f"Media asset {command.asset_id} not found"
                )

            await self._policy.check(command.target_type, asset)

            if asset.status is MediaStatus.STAGED:
                asset.promote()
                await repos.assets.save(asset)
                was_staged = True

            attachment = MediaAttachment.for_target(
                asset_id=asset.id,
                target_type=command.target_type,
                target_id=command.target_id,
                attribute_key=command.attribute_key,
            )
            await repos.attachments.add(attachment)
            await self._uow.commit()

        if was_staged:
            await self._storage.move(asset.id, MediaStatus.STAGED, MediaStatus.ATTACHED)

        return attachment
