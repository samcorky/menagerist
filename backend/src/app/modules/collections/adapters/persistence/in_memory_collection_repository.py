import unicodedata
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid

    from app.modules.collections.domain.collection import Collection, CollectionKind
    from app.shared_kernel.content_filter import ContentFilter


def _fold(text: str) -> str:
    """Casefold `text` and strip combining accents.

    Close to Postgres `lower(unaccent(...))` but not equal: letters `unaccent`
    transliterates without a combining mark (Æ, Ø, Ł, Đ, Þ and others) differ.
    """
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

    def owner_of(self, collection_id: uuid.UUID) -> uuid.UUID | None:
        """Return the owner of the stored collection, deleted or not, or `None`."""
        found = self._collections.get(collection_id)
        return None if found is None else found.owner_id

    @staticmethod
    def _visible(collection: Collection, scope: ContentFilter) -> bool:
        """Whether `collection` is live and its owner is inside `scope`."""
        return not collection.is_deleted and scope.covers(collection.owner_id)

    async def get(
        self, collection_id: uuid.UUID, *, scope: ContentFilter
    ) -> Collection | None:
        """Return the live collection with `collection_id` in `scope`, or `None`."""
        found = self._collections.get(collection_id)
        return found if found is not None and self._visible(found, scope) else None

    async def get_by_slug(
        self, slug: str, *, scope: ContentFilter
    ) -> Collection | None:
        """Return the live collection with `slug` in `scope`, or `None`."""
        return next(
            (
                c
                for c in sorted(self._collections.values(), key=lambda c: c.id)
                if self._visible(c, scope) and c.slug.value == slug
            ),
            None,
        )

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
        ignoring case and accents. A `kind` keeps only collections of that kind.
        """
        needle = _fold((q or "").strip())
        live = sorted(
            (
                c
                for c in self._collections.values()
                if self._visible(c, scope)
                and (after is None or c.id > after)
                and (kind is None or c.kind is kind)
                and (
                    not needle
                    or needle in _fold(c.name)
                    or needle in _fold(c.description or "")
                )
            ),
            key=lambda c: c.id,
        )
        return live[:limit]

    async def claim_orphaned(
        self, owner_id: uuid.UUID, *, legacy_owner_ids: frozenset[uuid.UUID]
    ) -> int:
        """Give `owner_id` every collection with no owner or a legacy owner."""
        claimed = [
            row
            for row in self._collections.values()
            if row.owner_id is None or row.owner_id in legacy_owner_ids
        ]
        for row in claimed:
            row.owner_id = owner_id
        return len(claimed)
