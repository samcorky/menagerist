from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid

    from app.modules.collections.domain.collection import Collection


class CollectionRepository(Protocol):
    """Access to collections, independent of storage backend.

    Reads return live (non-deleted) collections only.
    """

    async def add(self, collection: Collection) -> None:
        """Add a new collection."""
        ...

    async def save(self, collection: Collection) -> None:
        """Persist changes to an existing collection, including soft deletion."""
        ...

    async def get(self, collection_id: uuid.UUID) -> Collection | None:
        """Return the live collection with `collection_id`, or `None`."""
        ...

    async def get_by_slug(self, slug: str) -> Collection | None:
        """Return the live collection with `slug`, or `None`."""
        ...

    async def list(
        self, *, after: uuid.UUID | None, limit: int, q: str | None = None
    ) -> list[Collection]:
        """Return up to `limit` live collections ordered by id, after `after`.

        A non-blank `q` keeps collections whose name or description contains it,
        ignoring case.
        """
        ...
