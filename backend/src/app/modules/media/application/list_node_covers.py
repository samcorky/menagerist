import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from app.modules.media.application.permissions import MediaPermission
from app.modules.media.domain.media_asset import MediaAsset
from app.modules.media.domain.media_attachment import AttachmentTarget
from app.modules.media.ports.unit_of_work import MediaRepos
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class ListNodeCoversQuery:
    """Request for the cover of each of several items."""

    node_ids: list[uuid.UUID]


class ListNodeCovers(
    QueryHandler[MediaRepos, ListNodeCoversQuery, dict[uuid.UUID, MediaAsset]]
):
    """Return the cover asset of each item that has one, in a single lookup.

    A list of items shows many covers at once; asking item by item would make a
    request for every card.
    """

    access: ClassVar[Access] = Content(MediaPermission.ITEM_READ)

    async def _handle(
        self, query: ListNodeCoversQuery, actor: Actor
    ) -> dict[uuid.UUID, MediaAsset]:
        """Fetch the covers of the items named, leaving out items without one."""
        return await self._repos.attachments.list_cover_assets(
            AttachmentTarget.NODE, query.node_ids, scope=self.scope(actor)
        )
