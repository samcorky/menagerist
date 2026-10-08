from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid

    from app.modules.collections.domain.collection import Membership


class InMemoryMembershipRepository:
    """Dict-backed `MembershipRepository` for tests."""

    def __init__(self) -> None:
        self._memberships: dict[tuple[uuid.UUID, uuid.UUID], Membership] = {}

    async def add(self, membership: Membership) -> None:
        """Add a membership; adding an existing pair leaves one stored."""
        self._memberships.setdefault(
            (membership.collection_id, membership.item_id), membership
        )

    async def remove(self, collection_id: uuid.UUID, item_id: uuid.UUID) -> None:
        """Remove a membership; a missing pair is a no-op."""
        self._memberships.pop((collection_id, item_id), None)

    async def item_ids(self, collection_id: uuid.UUID) -> set[uuid.UUID]:
        """Return the ids of the items on `collection_id`."""
        return {i for c, i in self._memberships if c == collection_id}

    async def collection_ids_for(self, item_id: uuid.UUID) -> set[uuid.UUID]:
        """Return the ids of the collections holding `item_id`."""
        return {c for c, i in self._memberships if i == item_id}
