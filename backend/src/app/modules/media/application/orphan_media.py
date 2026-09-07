import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.media.domain.errors import MediaAssetNotFoundError
from app.modules.media.domain.media_asset import MediaAsset, MediaStatus
from app.modules.media.ports.unit_of_work import MediaUnitOfWork
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.modules.media.ports.media_storage import MediaStoragePort
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class OrphanMediaCommand:
    """Request to orphan an attached asset once it has been detached from all nodes."""

    asset_id: uuid.UUID


class OrphanMedia(CommandHandler[MediaUnitOfWork, OrphanMediaCommand, MediaAsset]):
    """Transition an attached asset to orphaned."""

    def __init__(self, uow: MediaUnitOfWork, storage: MediaStoragePort) -> None:
        super().__init__(uow)
        self._storage = storage

    async def handle(self, command: OrphanMediaCommand, actor: Actor) -> MediaAsset:
        """Transition the asset from attached to orphaned.

        Follows the same DB-first, then file-move ordering as `PromoteMedia`.
        """
        async with self._uow as repos:
            asset = await repos.assets.get(command.asset_id)
            if asset is None:
                raise MediaAssetNotFoundError(
                    f"Media asset {command.asset_id} not found"
                )
            asset.orphan()
            await repos.assets.save(asset)
            await self._uow.commit()
        await self._storage.move(asset.id, MediaStatus.ATTACHED, MediaStatus.ORPHANED)
        return asset
