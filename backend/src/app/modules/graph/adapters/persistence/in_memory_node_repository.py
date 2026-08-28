from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid

    from app.modules.graph.domain.node import Node


class InMemoryNodeRepository:
    """Dict-backed `NodeRepository` for tests and the in-memory adapter."""

    def __init__(self) -> None:
        self._nodes: dict[uuid.UUID, Node] = {}

    async def add(self, node: Node) -> None:
        """Add a new node."""
        self._nodes[node.id] = node

    async def save(self, node: Node) -> None:
        """Persist changes to an existing node."""
        self._nodes[node.id] = node

    async def get(self, node_id: uuid.UUID) -> Node | None:
        """Return the node with `node_id`, or `None` if missing or deleted."""
        node = self._nodes.get(node_id)
        if node is None or node.is_deleted:
            return None
        return node

    async def list(self, *, after: uuid.UUID | None, limit: int) -> list[Node]:
        """List non-deleted node ordered by id, starting after `after` if given."""
        ordered = sorted(
            (node for node in self._nodes.values() if not node.is_deleted),
            key=lambda node: node.id,
        )
        if after is not None:
            ordered = [node for node in ordered if node.id > after]
        return ordered[:limit]
