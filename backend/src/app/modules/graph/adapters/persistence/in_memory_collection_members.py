from typing import TYPE_CHECKING, Any

from app.modules.graph.ports.collection_members import (
    CollectionSource,
    ManualSource,
    SmartSource,
)

if TYPE_CHECKING:
    import uuid
    from collections.abc import Iterable, Mapping

    from app.shared_kernel.content_filter import ContentFilter


class InMemoryCollectionMembers:
    """Dict-backed CollectionMembers for tests."""

    def __init__(self) -> None:
        self._collections: dict[uuid.UUID, tuple[uuid.UUID, CollectionSource]] = {}

    def add_collection(
        self,
        collection_id: uuid.UUID,
        item_ids: Iterable[uuid.UUID],
        *,
        owner_id: uuid.UUID,
    ) -> None:
        """Register a manual collection owned by `owner_id` with the given item ids."""
        source = ManualSource(ids=frozenset(item_ids))
        self._collections[collection_id] = (owner_id, source)

    def add_smart_collection(
        self,
        collection_id: uuid.UUID,
        definition: Mapping[str, Any],
        *,
        owner_id: uuid.UUID,
    ) -> None:
        """Register a smart collection owned by `owner_id` with its definition."""
        source = SmartSource(definition=definition)
        self._collections[collection_id] = (owner_id, source)

    async def resolve(
        self, collection_id: uuid.UUID, scope: ContentFilter
    ) -> CollectionSource | None:
        """Return what the collection holds, or None if unknown or outside `scope`."""
        found = self._collections.get(collection_id)
        if found is None or not scope.covers(found[0]):
            return None
        return found[1]
