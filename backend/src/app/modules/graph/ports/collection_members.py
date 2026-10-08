from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid


class CollectionMembers(Protocol):
    """Read the item ids on a collection, owned by another module."""

    async def item_ids(self, collection_id: uuid.UUID) -> set[uuid.UUID] | None:
        """Return the item ids on the collection, or None if it does not exist."""
        ...
