from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import builtins
    import uuid
    from datetime import datetime

    from app.modules.graph.domain.node_type import NodeType
    from app.shared_kernel.content_filter import ContentFilter


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

    async def get(
        self, node_type_id: uuid.UUID, *, scope: ContentFilter
    ) -> NodeType | None:
        """Return the node type, or `None` if missing, deleted or outside `scope`."""
        nt = self._node_types.get(node_type_id)
        if nt is None or nt.is_deleted or not scope.covers(nt.owner_id):
            return None
        return nt

    async def get_for_removal(
        self, node_type_id: uuid.UUID, *, scope: ContentFilter
    ) -> NodeType | None:
        """Like `get`; the in-memory store has no concurrent writers to lock out."""
        return await self.get(node_type_id, scope=scope)

    async def get_by_slug(
        self, slug: str, *, scope: ContentFilter, guard_item_write: bool = False
    ) -> NodeType | None:
        """Return the node type with `slug` in `scope`, or `None` if missing/deleted."""
        return next(
            (
                nt
                for nt in self._node_types.values()
                if str(nt.slug) == slug
                and not nt.is_deleted
                and scope.covers(nt.owner_id)
            ),
            None,
        )

    async def list(
        self, *, scope: ContentFilter, after: uuid.UUID | None, limit: int
    ) -> list[NodeType]:
        """List non-deleted node types in `scope` ordered by id, after `after`."""
        ordered = sorted(
            (
                nt
                for nt in self._node_types.values()
                if not nt.is_deleted and scope.covers(nt.owner_id)
            ),
            key=lambda nt: nt.id,
        )
        if after is not None:
            ordered = [nt for nt in ordered if nt.id > after]
        return ordered[:limit]

    async def list_deleted_before(
        self, cutoff: datetime, *, after: uuid.UUID | None, limit: int
    ) -> builtins.list[NodeType]:
        """List rows soft-deleted before `cutoff`, ordered by id after `after`."""
        ordered = sorted(
            (
                nt
                for nt in self._node_types.values()
                if nt.deleted_at is not None and nt.deleted_at < cutoff
            ),
            key=lambda nt: nt.id,
        )
        if after is not None:
            ordered = [nt for nt in ordered if nt.id > after]
        return ordered[:limit]

    async def purge(self, node_type_id: uuid.UUID) -> None:
        """Hard-delete the row, live or soft-deleted; an unknown id is a no-op."""
        self._node_types.pop(node_type_id, None)

    async def claim_orphaned(
        self, owner_id: uuid.UUID, *, legacy_owner_ids: frozenset[uuid.UUID]
    ) -> int:
        """Give `owner_id` every node type with no owner or a legacy owner."""
        claimed = [
            row
            for row in self._node_types.values()
            if row.owner_id is None or row.owner_id in legacy_owner_ids
        ]
        for row in claimed:
            row.owner_id = owner_id
        return len(claimed)
