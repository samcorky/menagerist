from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.collections.application.permissions import CollectionPermission
from app.modules.collections.domain.collection import Collection
from app.modules.collections.ports.unit_of_work import CollectionsRepos
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import QueryHandler
from app.shared_kernel.paging import Cursor, PageRequest, SortOrder

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


class DeletedCollectionSort(StrEnum):
    """What the deleted collections can be sorted by: fields of the response."""

    DELETED_AT = "deleted_at"
    NAME = "name"


@dataclass(kw_only=True)
class ListDeletedCollectionsQuery:
    """Request for a page of deleted collections, newest deleted first unless told."""

    after: Cursor | None = None
    limit: int = 50
    sort: DeletedCollectionSort | None = None
    order: SortOrder = SortOrder.DESC


@dataclass(kw_only=True, frozen=True)
class ListDeletedCollectionsResult:
    """A page of deleted collections, the next cursor, and how many are deleted."""

    items: list[Collection]
    total: int
    next: Cursor | None = None


class ListDeletedCollections(
    QueryHandler[
        CollectionsRepos, ListDeletedCollectionsQuery, ListDeletedCollectionsResult
    ]
):
    """List the caller's deleted collections, newest deleted first."""

    access: ClassVar[Access] = Content(CollectionPermission.COLLECTION_READ)

    async def _handle(
        self, query: ListDeletedCollectionsQuery, actor: Actor
    ) -> ListDeletedCollectionsResult:
        """Return a page of deleted collections after `query.after`."""
        scope = self.scope(actor)
        sort = query.sort or DeletedCollectionSort.DELETED_AT
        page = await self._repos.collections.list_deleted(
            scope=scope,
            page=PageRequest(
                after=query.after,
                limit=query.limit,
                sort=sort.value,
                order=query.order,
            ),
        )
        total = await self._repos.collections.count_deleted(scope=scope)
        logger.debug("deleted collections listed", count=len(page.items), total=total)
        return ListDeletedCollectionsResult(
            items=page.items, total=total, next=page.next
        )
