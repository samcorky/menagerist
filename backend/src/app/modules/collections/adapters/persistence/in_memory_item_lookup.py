from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence


class InMemoryItemLookup:
    """`ItemLookup` over a settable set of live item ids, for tests."""

    def __init__(self, live: set[uuid.UUID] | None = None) -> None:
        self.live: set[uuid.UUID] = set(live or ())

    async def live_ids(self, ids: Sequence[uuid.UUID]) -> set[uuid.UUID]:
        """Return the subset of `ids` currently marked live."""
        return self.live.intersection(ids)
