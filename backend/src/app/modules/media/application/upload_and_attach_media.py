import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

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
    from app.modules.media.ports.media_storage import MediaStoragePort
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class UploadAndAttachMediaCommand:
    """Stage a new file and immediately attach it to a graph entity."""

    filename: str
    content_type: str
    stream: "AsyncIterator[bytes]"
    target_type: AttachmentTarget
    target_id: uuid.UUID
    attribute_key: AttachmentKey | None = field(default=None)
    max_size: int | None = field(default=None)


class UploadAndAttachMedia(
    CommandHandler[MediaUnitOfWork, UploadAndAttachMediaCommand, MediaAttachment]
):
    """Stream a file to storage, then attach it to a graph entity, atomically.

    Opens the real UoW once; runs both sub-handlers against a
    ``JoinedUnitOfWork`` wrapping its repos, so both DB writes land in a
    single transaction with a single commit.  Any deferred storage move
    registered via ``on_commit`` cannot fire ahead of the DB write it
    depends on, and will not fire at all if the transaction rolls back.
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
        self, command: UploadAndAttachMediaCommand, actor: Actor
    ) -> MediaAttachment:
        """Stage the file then immediately attach it within a single transaction."""
        async with self._uow as repos:
            joined = JoinedUnitOfWork(repos, owner=self._uow)

            stage = StageMedia(joined, self._storage)
            asset = await stage.handle(
                StageMediaCommand(
                    filename=command.filename,
                    content_type=command.content_type,
                    stream=command.stream,
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

        return attachment
