from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence

    from app.shared_kernel.actor import Actor


class ItemCovers(Protocol):
    """What other modules hold about the pictures of items shown in a list."""

    async def thumbnails(
        self, item_ids: Sequence[uuid.UUID], actor: Actor
    ) -> dict[uuid.UUID, str]:
        """Return where each item's cover thumbnail can be fetched.

        One lookup for every item. An item with no cover, or none the actor may
        see, or a cover with no thumbnail, is left out.
        """
        ...
