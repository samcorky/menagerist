from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid

    from app.modules.graph.domain.edge import Edge


class InMemoryEdgeRepository:
    """Dict-backed `EdgeRepository` for tests and the in-memory adapter."""

    def __init__(self) -> None:
        self._edges: dict[uuid.UUID, Edge] = {}

    async def add(self, edge: Edge) -> None:
        """Add a new edge."""
        self._edges[edge.id] = edge

    async def save(self, edge: Edge) -> None:
        """Persist changes to an existing edge."""
        self._edges[edge.id] = edge

    async def get(self, edge_id: uuid.UUID) -> Edge | None:
        """Return the edge with `edge_id`, or `None` if missing or deleted."""
        edge = self._edges.get(edge_id)
        if edge is None or edge.is_deleted:
            return None
        return edge

    async def list_for_node(
        self, node_id: uuid.UUID, *, after: uuid.UUID | None, limit: int
    ) -> list[Edge]:
        """List non-deleted edges where `node_id` is the source or target."""
        ordered = sorted(
            (
                edge
                for edge in self._edges.values()
                if not edge.is_deleted
                and (edge.source_id == node_id or edge.target_id == node_id)
            ),
            key=lambda edge: edge.id,
        )
        if after is not None:
            ordered = [edge for edge in ordered if edge.id > after]
        return ordered[:limit]

    async def list(self, *, after: uuid.UUID | None, limit: int) -> list[Edge]:
        """List non-deleted edges ordered by id, starting after `after` if given."""
        ordered = sorted(
            (edge for edge in self._edges.values() if not edge.is_deleted),
            key=lambda edge: edge.id,
        )
        if after is not None:
            ordered = [edge for edge in ordered if edge.id > after]
        return ordered[:limit]
