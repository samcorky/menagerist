import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.modules.media.domain.errors import MediaAssetNotFoundError
from app.modules.media.domain.media_asset import MediaAsset
from app.modules.media.ports.unit_of_work import MediaUnitOfWork
from app.shared_kernel.cqrs import ScopedCommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class UpdateMediaCommand:
    """Request to update an editable media attribute."""

    asset_id: uuid.UUID
    filename: str


class UpdateMedia(
    ScopedCommandHandler[MediaUnitOfWork, UpdateMediaCommand, MediaAsset]
):
    """Update a media asset's editable metadata."""

    async def handle(self, command: UpdateMediaCommand, actor: Actor) -> MediaAsset:
        """Persist the new filename for a media asset."""
        async with self._uow as repos:
            asset = await repos.assets.get(
                command.asset_id, scope=self._policy.scope_for(actor)
            )
            if asset is None:
                raise MediaAssetNotFoundError(
                    f"Media asset {command.asset_id} not found"
                )
            self._policy.assert_can_modify(actor, asset.owner_id)
            asset.rename(command.filename)
            await repos.assets.save(asset)
            await self._uow.commit()
        logger.info("media updated", asset_id=asset.id, filename=command.filename)
        return asset
