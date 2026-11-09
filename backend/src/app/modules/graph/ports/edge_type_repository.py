from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import builtins
    import uuid
    from datetime import datetime

    from app.modules.graph.domain.edge_type import EdgeType
    from app.shared_kernel.content_filter import ContentFilter


class EdgeTypeRepository(Protocol):
    """Write/read access to the edge type collection."""

    async def add(self, edge_type: EdgeType) -> None:
        """Persist a new edge type."""
        ...

    async def save(self, edge_type: EdgeType) -> None:
        """Persist changes to an existing edge type."""
        ...

    async def get(
        self, edge_type_id: uuid.UUID, *, scope: ContentFilter
    ) -> EdgeType | None:
        """Return the edge type, or None if missing, deleted or outside `scope`."""
        ...

    async def get_by_slug(self, slug: str, *, scope: ContentFilter) -> EdgeType | None:
        """Return the edge type with `slug` in `scope`, or None.

        A slug is unique per owner, so `scope` decides which person's type it is.
        """
        ...

    async def list(
        self, *, scope: ContentFilter, after: uuid.UUID | None, limit: int
    ) -> list[EdgeType]:
        """List non-deleted edge types in `scope` ordered by id."""
        ...

    async def list_deleted_before(
        self, cutoff: datetime, *, after: uuid.UUID | None, limit: int
    ) -> builtins.list[EdgeType]:
        """List relationship types deleted before `cutoff`, by id after `after`.

        System-level, for the retention purge.
        """
        ...

    async def purge(self, edge_type_id: uuid.UUID) -> None:
        """Hard-delete the row, live or soft-deleted; an unknown id is a no-op."""
        ...

    async def claim_orphaned(
        self, owner_id: uuid.UUID, *, legacy_owner_ids: frozenset[uuid.UUID]
    ) -> int:
        """Give `owner_id` every edge type with no owner or a legacy owner.

        System-level, for the first-admin claim; returns the number changed.
        """
        ...
