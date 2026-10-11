import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.modules.media.domain.errors import MediaAssetNotFoundError
from app.modules.media.domain.media_asset import MediaAsset, MediaStatus
from app.modules.media.ports.unit_of_work import MediaUnitOfWork
from app.shared_kernel.cqrs import ScopedCommandHandler

if TYPE_CHECKING:
    from app.modules.media.ports.media_storage import MediaStoragePort
    from app.shared_kernel.access_policy import AccessPolicy
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class PromoteMediaCommand:
    """Request to promote a staged asset to attached."""

    asset_id: uuid.UUID


class PromoteMedia(
    ScopedCommandHandler[MediaUnitOfWork, PromoteMediaCommand, MediaAsset]
):
    """Promote a staged asset to attached once it has been referenced by a node."""

    def __init__(
        self, uow: MediaUnitOfWork, policy: AccessPolicy, storage: MediaStoragePort
    ) -> None:
        super().__init__(uow, policy)
        self._storage = storage

    async def handle(self, command: PromoteMediaCommand, actor: Actor) -> MediaAsset:
        """Transition the asset from staged to attached.

        DB is updated and committed first; the file is then moved atomically.
        If the file move fails the record still reflects the new status, and
        the cleanup process can reconcile stale files.
        """
        async with self._uow as repos:
            asset = await repos.assets.get(
                command.asset_id, scope=self._policy.scope_for(actor)
            )
            if asset is None:
                raise MediaAssetNotFoundError(
                    f"Media asset {command.asset_id} not found"
                )
            self._policy.assert_can_modify(actor, asset.owner_id)
            asset.promote()
            await repos.assets.save(asset)
            await self._uow.commit()
        await self._storage.move(asset.id, MediaStatus.STAGED, MediaStatus.ATTACHED)
        logger.info("media promoted", asset_id=asset.id)
        return asset
