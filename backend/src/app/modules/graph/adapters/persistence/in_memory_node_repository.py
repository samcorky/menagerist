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

    async def list(
        self,
        *,
        after: uuid.UUID | None,
        limit: int,
        type: str | None = None,
        q: str | None = None,
        favourite: bool | None = None,
    ) -> list[Node]:
        """List non-deleted node ordered by id, starting after `after` if given."""
        ordered = sorted(
            (node for node in self._nodes.values() if not node.is_deleted),
            key=lambda node: node.id,
        )
        if type is not None:
            ordered = [node for node in ordered if node.type == type]
        if after is not None:
            ordered = [node for node in ordered if node.id > after]
        if q is not None:
            needle = q.casefold()
            ordered = [
                node
                for node in ordered
                if needle in node.name.casefold()
                or needle in (node.description or "").casefold()
            ]
        if favourite is not None:
            ordered = [node for node in ordered if node.favourite == favourite]
        return ordered[:limit]

    async def count(
        self,
        *,
        type: str | None = None,
        q: str | None = None,
        favourite: bool | None = None,
    ) -> int:
        """Return the total number of non-deleted nodes matching the given filters."""
        nodes = [n for n in self._nodes.values() if not n.is_deleted]
        if type is not None:
            nodes = [n for n in nodes if n.type == type]
        if q is not None:
            needle = q.casefold()
            nodes = [
                n
                for n in nodes
                if needle in n.name.casefold()
                or needle in (n.description or "").casefold()
            ]
        if favourite is not None:
            nodes = [n for n in nodes if n.favourite == favourite]
        return len(nodes)

    async def clear_type(self, type_slug: str) -> None:
        """Set `type` to None on all non-deleted nodes if type matches `type_slug`."""
        for node in self._nodes.values():
            if not node.is_deleted and node.type == type_slug:
                node.type = None
