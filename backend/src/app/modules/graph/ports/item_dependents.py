from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid


class ItemDependents(Protocol):
    """Remove what other modules hold about an item that is being purged."""

    async def purge_for_item(self, item_id: uuid.UUID) -> None:
        """Hard-delete the item's collection memberships and attachments.

        Media assets and stored files that only those attachments used go too.
        Safe to repeat.
        """
        ...
