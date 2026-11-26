from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.graph.application.permissions import GraphPermission
from app.modules.graph.domain.node import Node
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import QueryHandler
from app.shared_kernel.paging import Cursor, PageRequest, SortOrder

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


class DeletedNodeSort(StrEnum):
    """What the deleted items can be sorted by: fields of the response."""

    DELETED_AT = "deleted_at"
    NAME = "name"


@dataclass(kw_only=True)
class ListDeletedNodesQuery:
    """Request for a page of deleted items, newest deleted first unless told."""

    after: Cursor | None = None
    limit: int = 50
    sort: DeletedNodeSort | None = None
    order: SortOrder = SortOrder.DESC


@dataclass(frozen=True)
class ListDeletedNodesResult:
    """A page of deleted items, the next cursor, and how many are deleted."""

    items: list[Node]
    total: int
    next: Cursor | None = None


class ListDeletedNodes(
    QueryHandler[GraphRepos, ListDeletedNodesQuery, ListDeletedNodesResult]
):
    """List the caller's deleted items, newest deleted first."""

    access: ClassVar[Access] = Content(GraphPermission.ITEM_READ)

    async def _handle(
        self, query: ListDeletedNodesQuery, actor: Actor
    ) -> ListDeletedNodesResult:
        """Return a page of deleted items after `query.after`."""
        scope = self.scope(actor)
        sort = query.sort or DeletedNodeSort.DELETED_AT
        page = await self._repos.nodes.list_deleted(
            scope=scope,
            page=PageRequest(
                after=query.after,
                limit=query.limit,
                sort=sort.value,
                order=query.order,
            ),
        )
        total = await self._repos.nodes.count_deleted(scope=scope)
        logger.debug("deleted nodes listed", count=len(page.items), total=total)
        return ListDeletedNodesResult(items=page.items, total=total, next=page.next)
