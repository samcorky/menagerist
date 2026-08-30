from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid

    from app.modules.graph.domain.node_type import NodeType


class NodeTypeRepository(Protocol):
    """Access to node types, independent of storage backend."""

    async def add(self, node_type: NodeType) -> None:
        """Add a new node type."""
        ...

    async def save(self, node_type: NodeType) -> None:
        """Persist changes to an existing node type."""
        ...

    async def get(self, node_type_id: uuid.UUID) -> NodeType | None:
        """Return the node type with `node_type_id`, or `None` if missing or deleted."""
        ...

    async def get_by_slug(self, slug: str) -> NodeType | None:
        """Return the node type with `slug`, or `None` if missing or deleted."""
        ...

    async def list(self, *, after: uuid.UUID | None, limit: int) -> list[NodeType]:
        """List non-deleted node types ordered by id, starting after `after`."""
        ...
