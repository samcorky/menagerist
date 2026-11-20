from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import uuid
    from collections.abc import Mapping, Sequence

    from app.shared_kernel.content_filter import ContentFilter


class InMemoryItemLookup:
    """`ItemLookup` over settable live item ids, for tests.

    Ids in `live` are visible to every scope; `add_owned` registers items that
    only their owner's scope covers. A definition is not evaluated: every item
    inside the scope counts as matching, except pairs listed in `misses`.
    """

    def __init__(self, live: set[uuid.UUID] | None = None) -> None:
        self.live: set[uuid.UUID] = set(live or ())
        self.misses: list[tuple[Mapping[str, Any], uuid.UUID]] = []
        self._owners: dict[uuid.UUID, uuid.UUID] = {}

    def add_owned(self, item_id: uuid.UUID, owner_id: uuid.UUID) -> None:
        """Mark `item_id` live and visible only to `owner_id`'s scope."""
        self._owners[item_id] = owner_id

    async def live_ids(
        self, ids: Sequence[uuid.UUID], scope: ContentFilter
    ) -> set[uuid.UUID]:
        """Return the subset of `ids` that are live and inside `scope`."""
        owned = {i for i, owner in self._owners.items() if scope.covers(owner)}
        return (self.live | owned).intersection(ids)

    async def count_matching(
        self, definition: Mapping[str, Any], scope: ContentFilter, *, cap: int | None
    ) -> tuple[int, bool]:
        """Count the live items inside `scope`, up to `cap` (`None` for all)."""
        owned = {i for i, owner in self._owners.items() if scope.covers(owner)}
        total = len(self.live | owned)
        if cap is None:
            return total, False
        return min(total, cap), total > cap

    async def matches(
        self, definition: Mapping[str, Any], scope: ContentFilter, item_id: uuid.UUID
    ) -> bool:
        """Whether `item_id` is live in `scope` and not listed with `definition`."""
        if (definition, item_id) in self.misses:
            return False
        return bool(await self.live_ids([item_id], scope))
