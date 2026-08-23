from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid

    from app.modules.graph.domain.edge import Edge


class EdgeRepository(Protocol):
    """Access to edges, independent of storage backend."""

    async def add(self, edge: Edge) -> None:
        """Add a new edge."""
        ...

    async def save(self, edge: Edge) -> None:
        """Persist changes to an existing edge."""
        ...

    async def get(self, edge_id: uuid.UUID) -> Edge | None:
        """Return the edge with `edge_id`, or `None` if missing or deleted."""
        ...

    async def list_for_node(
        self, node_id: uuid.UUID, *, after: uuid.UUID | None, limit: int
    ) -> list[Edge]:
        """List non-deleted edges where `node_id` is the source or target."""
        ...

    async def list(self, *, after: uuid.UUID | None, limit: int) -> list[Edge]:
        """List non-deleted edges ordered by id, starting after `after` if given."""
        ...
