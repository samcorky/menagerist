from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid

    from app.modules.collections.domain.collection import Membership


class MembershipRepository(Protocol):
    """Access to collection memberships, independent of storage backend."""

    async def add(self, membership: Membership) -> None:
        """Add a membership; adding an existing pair leaves one stored."""
        ...

    async def remove(self, collection_id: uuid.UUID, item_id: uuid.UUID) -> None:
        """Remove a membership; a missing pair is a no-op."""
        ...

    async def item_ids(self, collection_id: uuid.UUID) -> set[uuid.UUID]:
        """Return the ids of the items on `collection_id`."""
        ...

    async def collection_ids_for(self, item_id: uuid.UUID) -> set[uuid.UUID]:
        """Return the ids of the collections holding `item_id`."""
        ...
