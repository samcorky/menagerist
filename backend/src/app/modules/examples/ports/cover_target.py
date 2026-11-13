from typing import TYPE_CHECKING, Protocol

from app.modules.transfer.ports.targets import Created, Inspection, RemoveResult  # noqa: TC001

if TYPE_CHECKING:
    import uuid


class CoverTarget(Protocol):
    """Creates, inspects and removes the generated covers of example items.

    For a cover, `Created.content` and `Inspection.content` are
    `{"style": ..., "name": ..., "sha256": ...}`; `sha256` is of the image's bytes,
    or `None` once the image is no longer the item's cover. So a replaced image
    reads as an edit. `Created.entity_id` identifies the cover itself, not the item.
    `Inspection.has_user_data` and `still_in_use` stay false.
    """

    async def create(self, item_id: uuid.UUID, name: str, style: str) -> Created:
        """Draw a cover for `name` in `style` and make it the item's cover."""
        ...

    async def inspect(self, cover_id: uuid.UUID) -> Inspection | None:
        """Return the cover as it is now, or `None` if it is gone."""
        ...

    async def remove(self, cover_id: uuid.UUID) -> RemoveResult:
        """Remove the cover and its stored files, or report that it is gone."""
        ...

    async def has_cover(self, item_id: uuid.UUID) -> bool:
        """Whether the item already has a cover image (a pack's or the person's)."""
        ...
