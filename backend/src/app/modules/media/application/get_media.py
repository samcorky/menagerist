import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.media.application.permissions import MediaPermission
from app.modules.media.domain.errors import MediaAssetNotFoundError
from app.modules.media.domain.media_asset import MediaAsset
from app.modules.media.ports.unit_of_work import MediaRepos
from app.shared_kernel.access import Access, Content
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

    access: ClassVar[Access] = Content(MediaPermission.ITEM_READ)

    async def _handle(self, query: GetMediaQuery, actor: Actor) -> MediaAsset:
        """Return the requested asset, raising `MediaAssetNotFoundError` if missing."""
        asset = await self._repos.assets.get(query.asset_id, scope=self.scope(actor))
        if asset is None:
            raise MediaAssetNotFoundError(f"Media asset {query.asset_id} not found")
        self._guard.assert_can_view(actor, asset.owner_id)
        logger.debug("media asset fetched", asset_id=query.asset_id)
        return asset
