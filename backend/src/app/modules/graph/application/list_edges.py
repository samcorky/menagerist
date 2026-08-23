import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.modules.graph.domain.edge import Edge
    from app.modules.graph.ports.edge_repository import EdgeRepository
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class ListEdgesQuery:
    """Request for a page of edges, ordered by id, optionally filtered to one node."""

    after: uuid.UUID | None = None
    limit: int = 50
    node_id: uuid.UUID | None = None


class ListEdges:
    """List edges with keyset pagination, optionally scoped to a single node."""

    def __init__(self, edges: EdgeRepository) -> None:
        self._edges = edges

    async def handle(self, query: ListEdgesQuery, actor: Actor) -> list[Edge]:
        """Return a page of edges after `query.after`, up to `query.limit`."""
        if query.node_id is not None:
            return await self._edges.list_for_node(
                query.node_id, after=query.after, limit=query.limit
            )
        return await self._edges.list(after=query.after, limit=query.limit)
