from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid

    from app.modules.collections.adapters.persistence.in_memory_collection_repository import (  # noqa: E501
        InMemoryCollectionRepository,
    )
    from app.modules.collections.domain.collection import Membership
    from app.shared_kernel.content_filter import ContentFilter


class InMemoryMembershipRepository:
    """Dict-backed `MembershipRepository` for tests.

    Reads the collection twin's owners to apply a scope, as the SQL twin joins them.
    """

    def __init__(self, collections: InMemoryCollectionRepository) -> None:
        self._collections = collections
        self._memberships: dict[tuple[uuid.UUID, uuid.UUID], Membership] = {}

    def _covered(self, collection_id: uuid.UUID, scope: ContentFilter) -> bool:
        """Whether the collection exists and its owner is inside `scope`."""
        owner = self._collections.owner_of(collection_id)
        return owner is not None and scope.covers(owner)

    async def add(self, membership: Membership) -> None:
        """Add a membership; adding an existing pair leaves one stored."""
        self._memberships.setdefault(
            (membership.collection_id, membership.item_id), membership
        )

    async def remove(self, collection_id: uuid.UUID, item_id: uuid.UUID) -> None:
        """Remove a membership; a missing pair is a no-op."""
        self._memberships.pop((collection_id, item_id), None)

    async def purge_for_collection(self, collection_id: uuid.UUID) -> None:
        """Remove every membership of the collection; none is a no-op."""
        self._memberships = {
            key: m for key, m in self._memberships.items() if key[0] != collection_id
        }

    async def purge_for_item(self, item_id: uuid.UUID) -> None:
        """Remove the item from every collection, soft-deleted ones included."""
        self._memberships = {
            key: m for key, m in self._memberships.items() if key[1] != item_id
        }

    async def item_ids(
        self, collection_id: uuid.UUID, *, scope: ContentFilter
    ) -> set[uuid.UUID]:
        """Return the item ids on `collection_id`; empty unless it is in `scope`."""
        if not self._covered(collection_id, scope):
            return set()
        return {i for c, i in self._memberships if c == collection_id}

    async def collection_ids_for(
        self, item_id: uuid.UUID, *, scope: ContentFilter
    ) -> set[uuid.UUID]:
        """Return the ids of the collections in `scope` holding `item_id`."""
        return {
            c for c, i in self._memberships if i == item_id and self._covered(c, scope)
        }
