from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid

    from app.modules.graph.domain.node import Node


class NodeRepository(Protocol):
    """Access to nodes, independent of storage backend."""

    async def add(self, node: Node) -> None:
        """Add a new node."""
        ...

    async def save(self, node: Node) -> None:
        """Persist changes to an existing node."""
        ...

    async def get(self, node_id: uuid.UUID) -> Node | None:
        """Return the node with `node_id`, or `None` if missing or deleted."""
        ...

    async def list(self, *, after: uuid.UUID | None, limit: int) -> list[Node]:
        """List non-deleted nodes ordered by id, starting after `after` if given."""
        ...
