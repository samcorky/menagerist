from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.graph.application.permissions import GraphPermission
from app.modules.graph.domain.node import Node
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import QueryHandler
from app.shared_kernel.paging import Page, SearchedPagedQuery, SortOrder

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


class DeletedNodeSort(StrEnum):
    """What the deleted items can be sorted by: fields of the response."""

    DELETED_AT = "deleted_at"
    NAME = "name"


@dataclass(kw_only=True)
class ListDeletedNodesQuery(SearchedPagedQuery[DeletedNodeSort]):
    """Request for a page of deleted items, newest deleted first unless told."""

    order: SortOrder = SortOrder.DESC


class ListDeletedNodes(QueryHandler[GraphRepos, ListDeletedNodesQuery, Page[Node]]):
    """List the caller's deleted items, newest deleted first."""

    access: ClassVar[Access] = Content(GraphPermission.ITEM_READ)

    async def _handle(self, query: ListDeletedNodesQuery, actor: Actor) -> Page[Node]:
        """Return a page of deleted items after `query.after`."""
        scope = self.scope(actor)
        page = await self._repos.nodes.list_deleted(
            scope=scope,
            page=query.page_request(DeletedNodeSort.DELETED_AT),
            q=query.q,
        )
        return page
