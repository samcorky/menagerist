import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.graph.application.permissions import GraphPermission
from app.modules.graph.domain.edge import Edge
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class ListEdgesQuery:
    """Request for a page of edge, ordered by id, optionally filtered to one node."""

    after: uuid.UUID | None = None
    limit: int = 50
    node_id: uuid.UUID | None = None


class ListEdges(QueryHandler[GraphRepos, ListEdgesQuery, list[Edge]]):
    """List edge with keyset pagination, optionally scoped to a single node."""

    access: ClassVar[Access] = Content(GraphPermission.ITEM_READ)

    async def _handle(self, query: ListEdgesQuery, actor: Actor) -> list[Edge]:
        """Return a page of edge after `query.after`, up to `query.limit`."""
        scope = self.scope(actor)
        if query.node_id is not None:
            edges = await self._repos.edges.list_for_node(
                query.node_id, scope=scope, after=query.after, limit=query.limit
            )
        else:
            edges = await self._repos.edges.list(
                scope=scope, after=query.after, limit=query.limit
            )
        logger.debug("edges listed", count=len(edges))
        return edges
