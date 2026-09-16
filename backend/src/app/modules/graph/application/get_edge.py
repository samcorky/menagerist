import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.modules.graph.domain.edge import Edge
from app.modules.graph.domain.errors import EdgeNotFoundError
from app.modules.graph.ports.unit_of_work import GraphRepos
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

    async def handle(self, query: GetEdgeQuery, actor: Actor) -> Edge:
        """Return the requested edge, raising `EdgeNotFoundError` if it's missing."""
        edge = await self._repos.edges.get(query.edge_id)
        if edge is None:
            raise EdgeNotFoundError(f"Edge {query.edge_id} not found")
        logger.debug("edge fetched", edge_id=query.edge_id)
        return edge
