import unicodedata
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid

    from app.modules.collections.domain.collection import Collection


def _fold(text: str) -> str:
    """Casefold `text` and strip accents, as Postgres `unaccent` does."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


class InMemoryCollectionRepository:
    """Dict-backed `CollectionRepository` for tests."""

    def __init__(self) -> None:
        self._collections: dict[uuid.UUID, Collection] = {}

    async def add(self, collection: Collection) -> None:
        """Add a new collection."""
        self._collections[collection.id] = collection

    async def save(self, collection: Collection) -> None:
        """Persist changes to an existing collection, including soft deletion."""
        self._collections[collection.id] = collection

    async def get(self, collection_id: uuid.UUID) -> Collection | None:
        """Return the live collection with `collection_id`, or `None`."""
        found = self._collections.get(collection_id)
        return found if found is not None and not found.is_deleted else None

    async def get_by_slug(self, slug: str) -> Collection | None:
        """Return the live collection with `slug`, or `None`."""
        return next(
            (
                c
                for c in self._collections.values()
                if not c.is_deleted and c.slug.value == slug
            ),
            None,
        )

    async def list(
        self, *, after: uuid.UUID | None, limit: int, q: str | None = None
    ) -> list[Collection]:
        """Return up to `limit` live collections ordered by id, after `after`.

        A non-blank `q` keeps collections whose name or description contains it,
        ignoring case and accents.
        """
        needle = _fold((q or "").strip())
        live = sorted(
            (
                c
                for c in self._collections.values()
                if not c.is_deleted
                and (after is None or c.id > after)
                and (
                    not needle
                    or needle in _fold(c.name)
                    or needle in _fold(c.description or "")
                )
            ),
            key=lambda c: c.id,
        )
        return live[:limit]
