from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.collections.application.permissions import CollectionPermission
from app.modules.collections.domain.collection import Collection
from app.modules.collections.ports.unit_of_work import CollectionsRepos
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import QueryHandler
from app.shared_kernel.paging import Page, SearchedPagedQuery, SortOrder

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


class DeletedCollectionSort(StrEnum):
    """What the deleted collections can be sorted by: fields of the response."""

    DELETED_AT = "deleted_at"
    NAME = "name"


@dataclass(kw_only=True)
class ListDeletedCollectionsQuery(SearchedPagedQuery[DeletedCollectionSort]):
    """Request for a page of deleted collections, newest deleted first unless told."""

    order: SortOrder = SortOrder.DESC


class ListDeletedCollections(
    QueryHandler[CollectionsRepos, ListDeletedCollectionsQuery, Page[Collection]]
):
    """List the caller's deleted collections, newest deleted first."""

    access: ClassVar[Access] = Content(CollectionPermission.COLLECTION_READ)

    async def _handle(
        self, query: ListDeletedCollectionsQuery, actor: Actor
    ) -> Page[Collection]:
        """Return a page of deleted collections after `query.after`."""
        scope = self.scope(actor)
        page = await self._repos.collections.list_deleted(
            scope=scope,
            page=query.page_request(DeletedCollectionSort.DELETED_AT),
            q=query.q,
        )
        logger.debug(
            "deleted collections listed", count=len(page.items), total=page.total
        )
        return page
