import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.graph.domain.edge import Edge
from app.modules.graph.domain.errors import EdgeNotFoundError
from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class GetEdgeQuery:
    """Request for a single edge by id."""

    edge_id: uuid.UUID


class GetEdge(QueryHandler[GraphUnitOfWork, GetEdgeQuery, Edge]):
    """Fetch a single edge by id."""

    async def handle(self, query: GetEdgeQuery, actor: Actor) -> Edge:
        """Return the requested edge, raising `EdgeNotFoundError` if it's missing."""
        async with self._uow as repos:
            edge = await repos.edges.get(query.edge_id)
        if edge is None:
            raise EdgeNotFoundError(f"Edge {query.edge_id} not found")
        return edge
