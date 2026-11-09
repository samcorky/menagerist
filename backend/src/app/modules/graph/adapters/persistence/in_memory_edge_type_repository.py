from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import builtins
    import uuid
    from datetime import datetime

    from app.modules.graph.domain.edge_type import EdgeType
    from app.shared_kernel.content_filter import ContentFilter


class InMemoryEdgeTypeRepository:
    """Dict-backed EdgeTypeRepository for tests."""

    def __init__(self) -> None:
        self._edge_types: dict[uuid.UUID, EdgeType] = {}

    async def add(self, edge_type: EdgeType) -> None:
        """Add a new edge type."""
        self._edge_types[edge_type.id] = edge_type

    async def save(self, edge_type: EdgeType) -> None:
        """Persist changes to an existing edge type."""
        self._edge_types[edge_type.id] = edge_type

    async def get(
        self, edge_type_id: uuid.UUID, *, scope: ContentFilter
    ) -> EdgeType | None:
        """Return the edge type, or None if missing, deleted or outside `scope`."""
        et = self._edge_types.get(edge_type_id)
        if et is None or et.is_deleted or not scope.covers(et.owner_id):
            return None
        return et

    async def get_by_slug(self, slug: str, *, scope: ContentFilter) -> EdgeType | None:
        """Return the edge type with `slug` in `scope`, or None if missing/deleted."""
        return next(
            (
                et
                for et in self._edge_types.values()
                if str(et.slug) == slug
                and not et.is_deleted
                and scope.covers(et.owner_id)
            ),
            None,
        )

    async def list(
        self, *, scope: ContentFilter, after: uuid.UUID | None, limit: int
    ) -> list[EdgeType]:
        """List non-deleted edge types in `scope` ordered by id, after `after`."""
        ordered = sorted(
            (
                et
                for et in self._edge_types.values()
                if not et.is_deleted and scope.covers(et.owner_id)
            ),
            key=lambda et: et.id,
        )
        if after is not None:
            ordered = [et for et in ordered if et.id > after]
        return ordered[:limit]

    async def list_deleted_before(
        self, cutoff: datetime, *, after: uuid.UUID | None, limit: int
    ) -> builtins.list[EdgeType]:
        """List rows soft-deleted before `cutoff`, ordered by id after `after`."""
        ordered = sorted(
            (
                et
                for et in self._edge_types.values()
                if et.deleted_at is not None and et.deleted_at < cutoff
            ),
            key=lambda et: et.id,
        )
        if after is not None:
            ordered = [et for et in ordered if et.id > after]
        return ordered[:limit]

    async def purge(self, edge_type_id: uuid.UUID) -> None:
        """Hard-delete the row, live or soft-deleted; an unknown id is a no-op."""
        self._edge_types.pop(edge_type_id, None)

    async def claim_orphaned(
        self, owner_id: uuid.UUID, *, legacy_owner_ids: frozenset[uuid.UUID]
    ) -> int:
        """Give `owner_id` every edge type with no owner or a legacy owner."""
        claimed = [
            row
            for row in self._edge_types.values()
            if row.owner_id is None or row.owner_id in legacy_owner_ids
        ]
        for row in claimed:
            row.owner_id = owner_id
        return len(claimed)
