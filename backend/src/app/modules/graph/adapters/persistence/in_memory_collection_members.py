from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid
    from collections.abc import Iterable


class InMemoryCollectionMembers:
    """Dict-backed CollectionMembers for tests."""

    def __init__(self) -> None:
        self._collections: dict[uuid.UUID, set[uuid.UUID]] = {}

    def add_collection(
        self, collection_id: uuid.UUID, item_ids: Iterable[uuid.UUID]
    ) -> None:
        """Register a collection with the given item ids."""
        self._collections[collection_id] = set(item_ids)

    async def item_ids(self, collection_id: uuid.UUID) -> set[uuid.UUID] | None:
        """Return a copy of the collection's item ids, or None if unknown."""
        ids = self._collections.get(collection_id)
        return None if ids is None else set(ids)
