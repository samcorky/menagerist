import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.modules.media.domain.media_asset import MediaAsset
from app.modules.media.domain.media_attachment import AttachmentKey, AttachmentTarget
from app.modules.media.ports.unit_of_work import MediaUnitOfWork
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class ListNodeMediaQuery:
    """Request for all media assets attached to a given node."""

    node_id: uuid.UUID


@dataclass
class NodeMediaItem:
    """A media asset paired with its attachment slot label."""

    asset: MediaAsset
    attribute_key: AttachmentKey | None


class ListNodeMedia(
    QueryHandler[MediaUnitOfWork, ListNodeMediaQuery, list[NodeMediaItem]]
):
    """Return all media assets currently attached to a node, with their slot labels."""

    async def handle(
        self, query: ListNodeMediaQuery, actor: Actor
    ) -> list[NodeMediaItem]:
        """Fetch attachments for the node then resolve each asset."""
        async with self._uow as repos:
            attachments = await repos.attachments.list_for_target(
                AttachmentTarget.NODE, query.node_id
            )
            results: list[NodeMediaItem] = []
            for att in attachments:
                asset = await repos.assets.get(att.asset_id)
                if asset is not None:
                    results.append(
                        NodeMediaItem(asset=asset, attribute_key=att.attribute_key)
                    )
        logger.debug("node media listed", node_id=query.node_id, count=len(results))
        return results
