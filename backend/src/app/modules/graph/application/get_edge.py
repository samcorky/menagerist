import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.graph.domain.errors import EdgeNotFoundError

if TYPE_CHECKING:
    from app.modules.graph.domain.edge import Edge
    from app.modules.graph.ports.edge_repository import EdgeRepository
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class GetEdgeQuery:
    """Request for a single edge by id."""

    edge_id: uuid.UUID


class GetEdge:
    """Fetch a single edge by id."""

    def __init__(self, edges: EdgeRepository) -> None:
        self._edges = edges

    async def handle(self, query: GetEdgeQuery, actor: Actor) -> Edge:
        """Return the requested edge, raising `EdgeNotFoundError` if it's missing."""
        edge = await self._edges.get(query.edge_id)
        if edge is None:
            raise EdgeNotFoundError(f"Edge {query.edge_id} not found")
        return edge
