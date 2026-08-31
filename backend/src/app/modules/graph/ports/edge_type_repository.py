from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid

    from app.modules.graph.domain.edge_type import EdgeType


class EdgeTypeRepository(Protocol):
    """Write/read access to the edge type collection."""

    async def add(self, edge_type: EdgeType) -> None:
        """Persist a new edge type."""
        ...

    async def save(self, edge_type: EdgeType) -> None:
        """Persist changes to an existing edge type."""
        ...

    async def get(self, edge_type_id: uuid.UUID) -> EdgeType | None:
        """Return the edge type with `edge_type_id`, or None."""
        ...

    async def get_by_slug(self, slug: str) -> EdgeType | None:
        """Return the edge type with `slug`, or None."""
        ...

    async def list(self, *, after: uuid.UUID | None, limit: int) -> list[EdgeType]:
        """List non-deleted edge types ordered by id."""
        ...
