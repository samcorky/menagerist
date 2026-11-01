from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import builtins
    import uuid
    from datetime import datetime

    from app.modules.collections.domain.collection import Collection, CollectionKind
    from app.shared_kernel.content_filter import ContentFilter


class CollectionRepository(Protocol):
    """Access to collections, independent of storage backend.

    Reads return live (non-deleted) collections only, inside the given scope.
    """

    async def add(self, collection: Collection) -> None:
        """Add a new collection."""
        ...

    async def save(self, collection: Collection) -> None:
        """Persist changes to an existing collection, including soft deletion."""
        ...

    async def get(
        self, collection_id: uuid.UUID, *, scope: ContentFilter
    ) -> Collection | None:
        """Return the live collection with `collection_id` in `scope`, or `None`."""
        ...

    async def get_by_slug(
        self, slug: str, *, scope: ContentFilter
    ) -> Collection | None:
        """Return the live collection with `slug` in `scope`, or `None`."""
        ...

    async def list(
        self,
        *,
        scope: ContentFilter,
        after: uuid.UUID | None,
        limit: int,
        q: str | None = None,
        kind: CollectionKind | None = None,
    ) -> list[Collection]:
        """Return up to `limit` live collections in `scope`, ordered by id.

        A non-blank `q` keeps collections whose name or description contains it,
        ignoring case. A `kind` keeps only collections of that kind.
        """
        ...

    async def get_deleted(
        self, collection_id: uuid.UUID, *, scope: ContentFilter
    ) -> Collection | None:
        """Return the soft-deleted collection with `collection_id`, or `None`."""
        ...

    async def list_deleted(
        self, *, scope: ContentFilter, after: uuid.UUID | None, limit: int
    ) -> builtins.list[Collection]:
        """List soft-deleted collections in `scope`, newest deleted first.

        Ties break by id. `after` is the id of the last row of the previous
        page; one no longer in Recently deleted yields an empty page.
        """
        ...

    async def count_deleted(self, *, scope: ContentFilter) -> int:
        """Return the number of soft-deleted collections in `scope`."""
        ...

    async def purge(self, collection_id: uuid.UUID) -> None:
        """Hard-delete the collection row, live or soft-deleted; unknown is a no-op.

        The caller purges its memberships first (`MembershipRepository`).
        """
        ...

    async def list_deleted_before(
        self, cutoff: datetime, *, limit: int
    ) -> builtins.list[Collection]:
        """List collections soft-deleted before `cutoff`, oldest first (ties by id).

        System-level and unscoped: every owner, for the retention purge.
        """
        ...

    async def count_deleted_before(self, cutoff: datetime) -> int:
        """Return how many collections were soft-deleted before `cutoff`, any owner."""
        ...

    async def claim_orphaned(
        self, owner_id: uuid.UUID, *, legacy_owner_ids: frozenset[uuid.UUID]
    ) -> int:
        """Give `owner_id` every collection with no owner or a legacy owner.

        System-level and unscoped, deleted rows included. Returns the count.
        """
        ...
