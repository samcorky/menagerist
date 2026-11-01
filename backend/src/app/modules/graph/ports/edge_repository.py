from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import builtins
    import uuid
    from datetime import datetime

    from app.modules.graph.domain.edge import Edge
    from app.shared_kernel.content_filter import ContentFilter


class EdgeRepository(Protocol):
    """Access to edge, independent of storage backend."""

    async def add(self, edge: Edge) -> None:
        """Add a new edge."""
        ...

    async def save(self, edge: Edge) -> None:
        """Persist changes to an existing edge."""
        ...

    async def get(self, edge_id: uuid.UUID, *, scope: ContentFilter) -> Edge | None:
        """Return the edge with `edge_id`, or `None` if missing, deleted or unseen."""
        ...

    async def list_for_node(
        self,
        node_id: uuid.UUID,
        *,
        scope: ContentFilter,
        after: uuid.UUID | None,
        limit: int,
    ) -> list[Edge]:
        """List non-deleted edge where `node_id` is the source or target."""
        ...

    async def list(
        self, *, scope: ContentFilter, after: uuid.UUID | None, limit: int
    ) -> list[Edge]:
        """List non-deleted edge ordered by id, starting after `after` if given."""
        ...

    async def has_edges_of_type(self, type_slug: str, *, scope: ContentFilter) -> bool:
        """Return True if any non-deleted edges reference `type_slug`."""
        ...

    async def count_with_attribute(
        self,
        type_slug: str,
        key: str,
        *,
        scope: ContentFilter,
        sub_key: str | None = None,
        value: str | None = None,
    ) -> int:
        """Count non-deleted edges of `type_slug` whose attributes contain `key`.

        With `value`, only those where the attribute equals that string. With
        `sub_key`, `key` names a group (array-of-objects) property and this
        counts edges where any row of that array holds `sub_key` (optionally
        equal to `value`), rather than `key` itself.
        """
        ...

    async def list_with_attribute(
        self,
        type_slug: str,
        key: str,
        *,
        scope: ContentFilter,
        sub_key: str | None = None,
        after: uuid.UUID | None,
        limit: int,
    ) -> builtins.list[Edge]:
        """List non-deleted edges of `type_slug` holding `key`, ordered by id.

        With `sub_key`, `key` names a group property and this lists edges
        where any row of that array holds `sub_key`.
        """
        ...

    async def purge(self, edge_id: uuid.UUID) -> None:
        """Hard-delete the edge row, live or soft-deleted; an unknown id is a no-op."""
        ...

    async def purge_for_node(self, node_id: uuid.UUID) -> None:
        """Hard-delete every edge, live or soft-deleted, touching `node_id`."""
        ...

    async def list_deleted_before(
        self, cutoff: datetime, *, limit: int
    ) -> builtins.list[Edge]:
        """List connections soft-deleted before `cutoff`, oldest first (ties by id).

        System-level and unscoped: every owner, for the retention purge.
        """
        ...

    async def count_deleted_before(self, cutoff: datetime) -> int:
        """Return how many connections were soft-deleted before `cutoff`, any owner."""
        ...

    async def claim_orphaned(
        self, owner_id: uuid.UUID, *, legacy_owner_ids: frozenset[uuid.UUID]
    ) -> int:
        """Give `owner_id` every connection with no owner or a legacy owner.

        System-level and unscoped, deleted rows included. Returns the count.
        """
        ...
