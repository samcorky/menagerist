from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid

    from app.shared_kernel.access_scope import AccessScope


class CollectionMembers(Protocol):
    """Read the item ids on a collection, owned by another module."""

    async def item_ids(
        self, collection_id: uuid.UUID, scope: AccessScope
    ) -> set[uuid.UUID] | None:
        """Return the item ids on the collection, or None if not visible in `scope`."""
        ...
