import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import structlog

from app.modules.media.application.attach_media import AttachMedia, AttachMediaCommand
from app.modules.media.application.stage_media import StageMedia, StageMediaCommand
from app.modules.media.domain.media_attachment import (
    AttachmentKey,
    AttachmentTarget,
    MediaAttachment,
)
from app.modules.media.ports.unit_of_work import MediaUnitOfWork
from app.shared_kernel.cqrs import CommandHandler
from app.shared_kernel.unit_of_work import JoinedUnitOfWork

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.modules.media.ports.attachment_policy import AttachmentPolicyPort
    from app.modules.media.ports.image_processor import ImageProcessorPort
    from app.modules.media.ports.media_storage import MediaStoragePort
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
    CommandHandler[MediaUnitOfWork, UploadAndAttachMediaCommand, MediaAttachment]
):
    """Stream a file to storage and attach it within a single transaction."""

    def __init__(
        self,
        uow: MediaUnitOfWork,
        storage: MediaStoragePort,
        policy: AttachmentPolicyPort,
        image_processor: ImageProcessorPort,
    ) -> None:
        super().__init__(uow)
        self._storage = storage
        self._policy = policy
        self._image_processor = image_processor

    async def handle(
        self, command: UploadAndAttachMediaCommand, actor: Actor
    ) -> MediaAttachment:
        """Stage the file then immediately attach it within a single transaction."""
        async with self._uow as repos:
            joined = JoinedUnitOfWork(repos, owner=self._uow)

            stage = StageMedia(joined, self._storage, self._image_processor)
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

            attach = AttachMedia(joined, self._storage, self._policy)
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
