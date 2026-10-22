import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.media.application.attach_media import AttachMedia, AttachMediaCommand
from app.modules.media.application.cover_guard import ensure_cover_free
from app.modules.media.application.stage_media import StageMedia, StageMediaCommand
from app.modules.media.domain.errors import AttachTargetNotFoundError
from app.modules.media.domain.media_attachment import (
    AttachmentKey,
    AttachmentTarget,
    MediaAttachment,
)
from app.modules.media.ports.unit_of_work import MediaUnitOfWork
from app.shared_kernel.access import Access, Content
from app.shared_kernel.guarded import GuardedCommandHandler
from app.shared_kernel.unit_of_work import JoinedUnitOfWork

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.modules.media.ports.attach_target_access import AttachTargetAccess
    from app.modules.media.ports.attachment_policy import AttachmentPolicyPort
    from app.modules.media.ports.image_processor import ImageProcessorPort
    from app.modules.media.ports.media_storage import MediaStoragePort
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class UploadAndAttachMediaCommand:
    """Stage a new file and immediately attach it to a graph entity."""

    filename: str
    content_type: str
    stream: "AsyncIterator[bytes]"
    target_type: AttachmentTarget
    target_id: uuid.UUID
    attribute_key: AttachmentKey | None = field(default=None)
    sniffed_content_type: str | None = field(default=None)
    max_size: int | None = field(default=None)


class UploadAndAttachMedia(
    GuardedCommandHandler[MediaUnitOfWork, UploadAndAttachMediaCommand, MediaAttachment]
):
    """Stream a file to storage and attach it within a single transaction."""

    access: ClassVar[Access] = Content()

    def __init__(
        self,
        uow: MediaUnitOfWork,
        guard: AccessGuard,
        storage: MediaStoragePort,
        attachment_policy: AttachmentPolicyPort,
        image_processor: ImageProcessorPort,
        targets: AttachTargetAccess,
    ) -> None:
        super().__init__(uow, guard)
        self._storage = storage
        self._attachment_policy = attachment_policy
        self._image_processor = image_processor
        self._targets = targets

    async def _handle(
        self, command: UploadAndAttachMediaCommand, actor: Actor
    ) -> MediaAttachment:
        """Stage the file then immediately attach it within a single transaction."""
        scope = self.scope(actor)
        # Checked before streaming so a refused upload leaves no file behind.
        if not await self._targets.can_attach(
            command.target_type, command.target_id, scope
        ):
            raise AttachTargetNotFoundError(
                f"{command.target_type} {command.target_id} not found"
            )
        async with self._uow as repos:
            await ensure_cover_free(
                repos.attachments,
                attribute_key=command.attribute_key,
                target_type=command.target_type,
                target_id=command.target_id,
                scope=scope,
            )
            joined = JoinedUnitOfWork(repos, owner=self._uow)

            stage = StageMedia(
                joined, self._guard, self._storage, self._image_processor
            )
            asset = await stage.handle(
                StageMediaCommand(
                    filename=command.filename,
                    content_type=command.content_type,
                    stream=command.stream,
                    sniffed_content_type=command.sniffed_content_type,
                    max_size=command.max_size,
                ),
                actor,
            )

            attach = AttachMedia(
                joined,
                self._guard,
                self._storage,
                self._attachment_policy,
                self._targets,
            )
            attachment = await attach.handle(
                AttachMediaCommand(
                    asset_id=asset.id,
                    target_type=command.target_type,
                    target_id=command.target_id,
                    attribute_key=command.attribute_key,
                ),
                actor,
            )

            await self._uow.commit()

        logger.info(
            "media uploaded and attached",
            asset_id=attachment.asset_id,
            target_type=command.target_type.value,
            target_id=command.target_id,
        )
        return attachment
