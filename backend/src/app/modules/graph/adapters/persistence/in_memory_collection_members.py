from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid
    from collections.abc import Iterable

    from app.shared_kernel.access_scope import AccessScope


class InMemoryCollectionMembers:
    """Dict-backed CollectionMembers for tests."""

    def __init__(self) -> None:
        self._collections: dict[uuid.UUID, tuple[uuid.UUID, set[uuid.UUID]]] = {}

    def add_collection(
        self,
        collection_id: uuid.UUID,
        item_ids: Iterable[uuid.UUID],
        *,
        owner_id: uuid.UUID,
    ) -> None:
        """Register a collection owned by `owner_id` with the given item ids."""
        self._collections[collection_id] = (owner_id, set(item_ids))

    async def item_ids(
        self, collection_id: uuid.UUID, scope: AccessScope
    ) -> set[uuid.UUID] | None:
        """Return a copy of the item ids, or None if unknown or outside `scope`."""
        found = self._collections.get(collection_id)
        if found is None or not scope.covers(found[0]):
            return None
        return set(found[1])
