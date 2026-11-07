from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid

    from app.shared_kernel.actor import Actor


class ItemCompanions(Protocol):
    """Copy what other modules hold about an item onto its duplicate."""

    async def copy_media(
        self,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        *,
        attachments: bool,
        cover: bool,
        actor: Actor,
    ) -> None:
        """Give the target its own copies of the source's media files.

        With `attachments`, every attachment except the cover is copied; with
        `cover`, the cover is copied and stays the target's cover. The copies are
        independent files, so deleting one item's photo never affects the other.
        """
        ...

    async def copy_collections(
        self, source_id: uuid.UUID, target_id: uuid.UUID, *, actor: Actor
    ) -> None:
        """Add the target to every manual collection the source is in."""
        ...
