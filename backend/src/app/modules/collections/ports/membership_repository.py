from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid

    from app.modules.collections.domain.collection import Membership
    from app.shared_kernel.content_filter import ContentFilter


class MembershipRepository(Protocol):
    """Access to collection memberships, independent of storage backend.

    A membership carries no owner of its own: reads follow the owner of its
    collection, through the given scope.
    """

    async def add(self, membership: Membership) -> None:
        """Add a membership; adding an existing pair leaves one stored."""
        ...

    async def remove(self, collection_id: uuid.UUID, item_id: uuid.UUID) -> None:
        """Remove a membership; a missing pair is a no-op."""
        ...

    async def purge_for_collection(self, collection_id: uuid.UUID) -> None:
        """Remove every membership of the collection; none is a no-op."""
        ...

    async def purge_for_item(self, item_id: uuid.UUID) -> None:
        """Remove the item from every collection, soft-deleted ones included."""
        ...

    async def item_ids(
        self, collection_id: uuid.UUID, *, scope: ContentFilter
    ) -> set[uuid.UUID]:
        """Return the item ids on `collection_id`; empty unless it is in `scope`.

        Memberships outlive a soft-deleted collection, so those are still returned.
        """
        ...

    async def collection_ids_for(
        self, item_id: uuid.UUID, *, scope: ContentFilter
    ) -> set[uuid.UUID]:
        """Return the ids of the collections in `scope` holding `item_id`.

        Soft-deleted collections are included: callers filter on liveness.
        """
        ...
