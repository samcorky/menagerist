from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence


class ItemLookup(Protocol):
    """Read-only view of which items exist, owned by another module."""

    async def live_ids(self, ids: Sequence[uuid.UUID]) -> set[uuid.UUID]:
        """Return the subset of `ids` that are live (non-deleted) items."""
        ...
