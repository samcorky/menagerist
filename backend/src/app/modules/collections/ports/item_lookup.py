from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence

    from app.shared_kernel.access_scope import AccessScope


class ItemLookup(Protocol):
    """Read-only view of which items exist, owned by another module."""

    async def live_ids(
        self, ids: Sequence[uuid.UUID], scope: AccessScope
    ) -> set[uuid.UUID]:
        """Return the subset of `ids` that are live items inside `scope`."""
        ...
