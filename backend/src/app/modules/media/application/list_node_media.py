import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.media.domain.media_asset import MediaAsset
from app.modules.media.domain.media_attachment import AttachmentTarget
from app.modules.media.ports.unit_of_work import MediaUnitOfWork
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class ListNodeMediaQuery:
    """Request for all media assets attached to a given node."""

    node_id: uuid.UUID


class ListNodeMedia(
    QueryHandler[MediaUnitOfWork, ListNodeMediaQuery, list[MediaAsset]]
):
    """Return all media assets currently attached to a node."""

    async def handle(self, query: ListNodeMediaQuery, actor: Actor) -> list[MediaAsset]:
        """Fetch attachments for the node then resolve each asset."""
        async with self._uow as repos:
            attachments = await repos.attachments.list_for_target(
                AttachmentTarget.NODE, query.node_id
            )
            assets: list[MediaAsset] = []
            for att in attachments:
                asset = await repos.assets.get(att.asset_id)
                if asset is not None:
                    assets.append(asset)
        return assets
