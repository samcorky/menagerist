import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.modules.media.domain.errors import MediaAssetNotFoundError
from app.modules.media.domain.media_asset import MediaAsset
from app.modules.media.ports.unit_of_work import MediaRepos
from app.shared_kernel.cqrs import ScopedQueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class GetMediaQuery:
    """Request for a single media asset by id."""

    asset_id: uuid.UUID


class GetMedia(ScopedQueryHandler[MediaRepos, GetMediaQuery, MediaAsset]):
    """Fetch a single media asset by id."""

    async def handle(self, query: GetMediaQuery, actor: Actor) -> MediaAsset:
        """Return the requested asset, raising `MediaAssetNotFoundError` if missing."""
        asset = await self._repos.assets.get(
            query.asset_id, scope=self._policy.scope_for(actor)
        )
        if asset is None:
            raise MediaAssetNotFoundError(f"Media asset {query.asset_id} not found")
        self._policy.assert_can_view(actor, asset.owner_id)
        logger.debug("media asset fetched", asset_id=query.asset_id)
        return asset
