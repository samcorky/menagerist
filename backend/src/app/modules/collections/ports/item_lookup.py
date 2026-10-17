from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    import uuid
    from collections.abc import Mapping, Sequence

    from app.shared_kernel.access_scope import AccessScope


class ItemLookup(Protocol):
    """Read-only view of which items exist, owned by another module."""

    async def live_ids(
        self, ids: Sequence[uuid.UUID], scope: AccessScope
    ) -> set[uuid.UUID]:
        """Return the subset of `ids` that are live items inside `scope`."""
        ...

    async def count_matching(
        self, definition: Mapping[str, Any], scope: AccessScope, *, cap: int
    ) -> tuple[int, bool]:
        """Return how many items in `scope` match `definition`, and if capped.

        The count stops at `cap`. A stale definition matches nothing, and one
        that cannot be read counts as `(0, False)`; neither raises.
        """
        ...
