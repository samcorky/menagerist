import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.graph.application.permissions import GraphPermission
from app.modules.graph.domain.edge import Edge
from app.modules.graph.domain.errors import EdgeNotFoundError
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class GetEdgeQuery:
    """Request for a single edge by id."""

    edge_id: uuid.UUID


class GetEdge(QueryHandler[GraphRepos, GetEdgeQuery, Edge]):
    """Fetch a single edge by id."""

    access: ClassVar[Access] = Content(GraphPermission.ITEM_READ)

    async def _handle(self, query: GetEdgeQuery, actor: Actor) -> Edge:
        """Return the requested edge, raising `EdgeNotFoundError` if it's missing."""
        edge = await self._repos.edges.get(query.edge_id, scope=self.scope(actor))
        if edge is None:
            raise EdgeNotFoundError(f"Edge {query.edge_id} not found")
        self._guard.assert_can_view(actor, edge.owner_id)
        logger.debug("edge fetched", edge_id=query.edge_id)
        return edge
