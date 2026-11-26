import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.graph.application.permissions import GraphPermission
from app.modules.graph.domain.edge import Edge
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import QueryHandler
from app.shared_kernel.paging import Page, PagedQuery

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


class EdgeSort(StrEnum):
    """What a list of connections can be sorted by: fields of the response."""

    TYPE = "type"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


@dataclass(kw_only=True)
class ListEdgesQuery(PagedQuery[EdgeSort]):
    """Request for a page of edges, by id unless `sort` says, optionally of one node."""

    node_id: uuid.UUID | None = None


class ListEdges(QueryHandler[GraphRepos, ListEdgesQuery, Page[Edge]]):
    """List edge with keyset pagination, optionally scoped to a single node."""

    access: ClassVar[Access] = Content(GraphPermission.ITEM_READ)

    async def _handle(self, query: ListEdgesQuery, actor: Actor) -> Page[Edge]:
        """Return a page of edges after `query.after`, up to `query.limit`."""
        scope = self.scope(actor)
        request = query.page_request()
        if query.node_id is not None:
            page = await self._repos.edges.page_for_node(
                query.node_id, scope=scope, page=request
            )
        else:
            page = await self._repos.edges.list(scope=scope, page=request)
        logger.debug("edges listed", count=len(page.items))
        return page
