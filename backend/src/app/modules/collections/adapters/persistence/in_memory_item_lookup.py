from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence

    from app.shared_kernel.access_scope import AccessScope


class InMemoryItemLookup:
    """`ItemLookup` over settable live item ids, for tests.

    Ids in `live` are visible to every scope; `add_owned` registers items that
    only their owner's scope covers.
    """

    def __init__(self, live: set[uuid.UUID] | None = None) -> None:
        self.live: set[uuid.UUID] = set(live or ())
        self._owners: dict[uuid.UUID, uuid.UUID] = {}

    def add_owned(self, item_id: uuid.UUID, owner_id: uuid.UUID) -> None:
        """Mark `item_id` live and visible only to `owner_id`'s scope."""
        self._owners[item_id] = owner_id

    async def live_ids(
        self, ids: Sequence[uuid.UUID], scope: AccessScope
    ) -> set[uuid.UUID]:
        """Return the subset of `ids` that are live and inside `scope`."""
        owned = {i for i, owner in self._owners.items() if scope.covers(owner)}
        return (self.live | owned).intersection(ids)
