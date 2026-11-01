from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid


class PresetUsage(Protocol):
    """Find the item types that still reference a preset, owned by another module."""

    async def types_using(self, preset_id: uuid.UUID) -> list[str]:
        """Return the labels of the item types that reference `preset_id`."""
        ...
