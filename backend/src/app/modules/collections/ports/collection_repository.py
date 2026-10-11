from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid

    from app.modules.collections.domain.collection import Collection
    from app.shared_kernel.access_scope import AccessScope


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
        self, collection_id: uuid.UUID, *, scope: AccessScope
    ) -> Collection | None:
        """Return the live collection with `collection_id` in `scope`, or `None`."""
        ...

    async def get_by_slug(self, slug: str, *, scope: AccessScope) -> Collection | None:
        """Return the live collection with `slug` in `scope`, or `None`."""
        ...

    async def list(
        self,
        *,
        scope: AccessScope,
        after: uuid.UUID | None,
        limit: int,
        q: str | None = None,
    ) -> list[Collection]:
        """Return up to `limit` live collections in `scope`, ordered by id.

        A non-blank `q` keeps collections whose name or description contains it,
        ignoring case.
        """
        ...

    async def claim_orphaned(
        self, owner_id: uuid.UUID, *, legacy_owner_ids: frozenset[uuid.UUID]
    ) -> int:
        """Give `owner_id` every collection with no owner or a legacy owner.

        System-level and unscoped, deleted rows included. Returns the count.
        """
        ...
