import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.modules.media.domain.errors import MediaAssetNotFoundError
from app.modules.media.domain.media_asset import MediaAsset
from app.modules.media.ports.unit_of_work import MediaRepos
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class GetMediaQuery:
    """Request for a single media asset by id."""

    asset_id: uuid.UUID


class GetMedia(QueryHandler[MediaRepos, GetMediaQuery, MediaAsset]):
    """Fetch a single media asset by id."""

    async def handle(self, query: GetMediaQuery, actor: Actor) -> MediaAsset:
        """Return the requested asset, raising `MediaAssetNotFoundError` if missing."""
        asset = await self._repos.assets.get(query.asset_id)
        if asset is None:
            raise MediaAssetNotFoundError(f"Media asset {query.asset_id} not found")
        logger.debug("media asset fetched", asset_id=query.asset_id)
        return asset
