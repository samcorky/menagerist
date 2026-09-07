import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.modules.media.domain.media_asset import MediaAsset, MediaStatus
from app.modules.media.ports.unit_of_work import MediaUnitOfWork
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.modules.media.ports.media_storage import MediaStoragePort
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class StageMediaCommand:
    """Request to stage a new media upload."""

    filename: str
    content_type: str
    stream: "AsyncIterator[bytes]"
    max_size: int | None = field(default=None)


class StageMedia(CommandHandler[MediaUnitOfWork, StageMediaCommand, MediaAsset]):
    """Stream an upload to staging storage and record it in the database."""

    def __init__(self, uow: MediaUnitOfWork, storage: MediaStoragePort) -> None:
        super().__init__(uow)
        self._storage = storage

    async def handle(self, command: StageMediaCommand, actor: Actor) -> MediaAsset:
        """Write the stream to staged storage, then persist the asset record.

        The id is pre-generated so the storage adapter knows the destination path
        before the DB row is written.
        """
        asset_id = uuid.uuid7()
        size, sha256 = await self._storage.store(
            asset_id,
            MediaStatus.STAGED,
            command.stream,
            max_size=command.max_size,
        )
        asset = MediaAsset.create(
            asset_id=asset_id,
            filename=command.filename,
            content_type=command.content_type,
            size=size,
            sha256=sha256,
        )
        async with self._uow as repos:
            await repos.assets.add(asset)
            await self._uow.commit()
        return asset
