import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.modules.media.application.attach_media import AttachMedia, AttachMediaCommand
from app.modules.media.application.stage_media import StageMedia, StageMediaCommand
from app.modules.media.domain.media_attachment import AttachmentTarget, MediaAttachment
from app.modules.media.ports.unit_of_work import MediaUnitOfWork
from app.shared_kernel.cqrs import CommandHandler

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
    attribute_key: str | None = field(default=None)
    max_size: int | None = field(default=None)


class UploadAndAttachMedia(
    CommandHandler[MediaUnitOfWork, UploadAndAttachMediaCommand, MediaAttachment]
):
    """Stream a file to storage, then attach it to a graph entity in one shot.

    Delegates to `StageMedia` then `AttachMedia`. The two use-cases share the
    same `uow` instance so they operate within the same session.
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
        """Stage the file then immediately attach it to the target entity."""
        stage = StageMedia(self._uow, self._storage)
        asset = await stage.handle(
            StageMediaCommand(
                filename=command.filename,
                content_type=command.content_type,
                stream=command.stream,
                max_size=command.max_size,
            ),
            actor,
        )

        attach = AttachMedia(self._uow, self._storage, self._policy)
        return await attach.handle(
            AttachMediaCommand(
                asset_id=asset.id,
                target_type=command.target_type,
                target_id=command.target_id,
                attribute_key=command.attribute_key,
            ),
            actor,
        )
