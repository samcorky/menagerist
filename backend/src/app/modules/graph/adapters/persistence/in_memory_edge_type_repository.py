from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import builtins
    import uuid
    from datetime import datetime

    from app.modules.graph.domain.edge_type import EdgeType


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

    async def get(self, edge_type_id: uuid.UUID) -> EdgeType | None:
        """Return the edge type with `edge_type_id`, or None if missing or deleted."""
        et = self._edge_types.get(edge_type_id)
        if et is None or et.is_deleted:
            return None
        return et

    async def get_by_slug(self, slug: str) -> EdgeType | None:
        """Return the edge type with `slug`, or None if missing or deleted."""
        return next(
            (
                et
                for et in self._edge_types.values()
                if str(et.slug) == slug and not et.is_deleted
            ),
            None,
        )

    async def list(self, *, after: uuid.UUID | None, limit: int) -> list[EdgeType]:
        """List non-deleted edge types ordered by id, starting after `after`."""
        ordered = sorted(
            (et for et in self._edge_types.values() if not et.is_deleted),
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
