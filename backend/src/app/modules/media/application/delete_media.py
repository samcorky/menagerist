import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.media.domain.errors import MediaAssetNotFoundError
from app.modules.media.ports.unit_of_work import MediaUnitOfWork
from app.shared_kernel.access import Access, Content
from app.shared_kernel.guarded import GuardedCommandHandler

if TYPE_CHECKING:
    from app.modules.media.domain.media_asset import MediaAsset
    from app.modules.media.ports.media_storage import MediaStoragePort
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class DeleteMediaCommand:
    """Request to hard-delete a media asset."""

    asset_id: uuid.UUID


class DeleteMedia(GuardedCommandHandler[MediaUnitOfWork, DeleteMediaCommand, None]):
    """Hard-delete a media asset from both the database and storage."""

    access: ClassVar[Access] = Content()

    def __init__(
        self, uow: MediaUnitOfWork, guard: AccessGuard, storage: MediaStoragePort
    ) -> None:
        super().__init__(uow, guard)
        self._storage = storage

    async def _handle(self, command: DeleteMediaCommand, actor: Actor) -> None:
        """Remove the asset record, then delete its file.

        DB is removed first so any concurrent read immediately gets a 404.
        If the file delete subsequently fails the file is unreachable (no DB
        record) and will not be picked up by the cleanup job.
        """
        async with self._uow as repos:
            maybe = await repos.assets.get(command.asset_id, scope=self.scope(actor))
            if maybe is None:
                raise MediaAssetNotFoundError(
                    f"Media asset {command.asset_id} not found"
                )
            asset: MediaAsset = maybe
            self._guard.assert_can_delete(actor, asset.owner_id)
            await repos.assets.delete(asset.id)
            await self._uow.commit()
        await self._storage.delete(asset.id, asset.status)
        logger.info("media deleted", asset_id=command.asset_id)
