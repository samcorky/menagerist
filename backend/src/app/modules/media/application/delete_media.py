import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.media.domain.errors import MediaAssetNotFoundError
from app.modules.media.ports.unit_of_work import MediaUnitOfWork
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.modules.media.domain.media_asset import MediaAsset
    from app.modules.media.ports.media_storage import MediaStoragePort
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class DeleteMediaCommand:
    """Request to hard-delete a media asset."""

    asset_id: uuid.UUID


class DeleteMedia(CommandHandler[MediaUnitOfWork, DeleteMediaCommand, None]):
    """Hard-delete a media asset from both the database and storage."""

    def __init__(self, uow: MediaUnitOfWork, storage: MediaStoragePort) -> None:
        super().__init__(uow)
        self._storage = storage

    async def handle(self, command: DeleteMediaCommand, actor: Actor) -> None:
        """Remove the asset record, then delete its file.

        DB is removed first so any concurrent read immediately gets a 404.
        If the file delete subsequently fails the file is unreachable (no DB
        record) and will not be picked up by the cleanup job.
        """
        async with self._uow as repos:
            maybe = await repos.assets.get(command.asset_id)
            if maybe is None:
                raise MediaAssetNotFoundError(
                    f"Media asset {command.asset_id} not found"
                )
            asset: MediaAsset = maybe
            await repos.assets.delete(asset.id)
            await self._uow.commit()
        await self._storage.delete(asset.id, asset.status)
