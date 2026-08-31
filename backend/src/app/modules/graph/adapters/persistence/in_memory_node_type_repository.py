from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid

    from app.modules.graph.domain.node_type import NodeType


class InMemoryNodeTypeRepository:
    """Dict-backed `NodeTypeRepository` for tests and the in-memory adapter."""

    def __init__(self) -> None:
        self._node_types: dict[uuid.UUID, NodeType] = {}

    async def add(self, node_type: NodeType) -> None:
        """Add a new node type."""
        self._node_types[node_type.id] = node_type

    async def save(self, node_type: NodeType) -> None:
        """Persist changes to an existing node type."""
        self._node_types[node_type.id] = node_type

    async def get(self, node_type_id: uuid.UUID) -> NodeType | None:
        """Return the node type with `node_type_id`, or `None` if missing or deleted."""
        nt = self._node_types.get(node_type_id)
        if nt is None or nt.is_deleted:
            return None
        return nt

    async def get_by_slug(self, slug: str) -> NodeType | None:
        """Return the node type with `slug`, or `None` if missing or deleted."""
        return next(
            (
                nt
                for nt in self._node_types.values()
                if str(nt.slug) == slug and not nt.is_deleted
            ),
            None,
        )

    async def list(self, *, after: uuid.UUID | None, limit: int) -> list[NodeType]:
        """List non-deleted node types ordered by id, starting after `after`."""
        ordered = sorted(
            (nt for nt in self._node_types.values() if not nt.is_deleted),
            key=lambda nt: nt.id,
        )
        if after is not None:
            ordered = [nt for nt in ordered if nt.id > after]
        return ordered[:limit]
