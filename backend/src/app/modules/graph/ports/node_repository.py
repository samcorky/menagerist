from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid

    from app.modules.graph.domain.node import Node


class NodeRepository(Protocol):
    """Access to node, independent of storage backend."""

    async def add(self, node: Node) -> None:
        """Add a new node."""
        ...

    async def save(self, node: Node) -> None:
        """Persist changes to an existing node."""
        ...

    async def get(self, node_id: uuid.UUID) -> Node | None:
        """Return the node with `node_id`, or `None` if missing or deleted."""
        ...

    async def list(
        self,
        *,
        after: uuid.UUID | None,
        limit: int,
        type: str | None = None,
        q: str | None = None,
    ) -> list[Node]:
        """List non-deleted node ordered by id, starting after `after` if given."""
        ...

    async def count(self, *, type: str | None = None, q: str | None = None) -> int:
        """Return the total number of non-deleted nodes matching the given filters."""
        ...

    async def clear_type(self, type_slug: str) -> None:
        """Null out `type` on all non-deleted nodes that reference `type_slug`."""
        ...
