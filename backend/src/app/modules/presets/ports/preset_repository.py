from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid

    from app.modules.presets.domain.preset import Preset


class PresetRepository(Protocol):
    """Access to preset, independent of storage backend."""

    async def add(self, preset: Preset) -> None:
        """Add a new preset."""
        ...

    async def save(self, preset: Preset) -> None:
        """Persist changes to an existing preset."""
        ...

    async def get(self, preset_id: uuid.UUID) -> Preset | None:
        """Return the preset with `preset_id`, or `None` if missing or deleted."""
        ...

    async def list(
        self,
        *,
        after: uuid.UUID | None,
        limit: int,
        kind: str | None = None,
        q: str | None = None,
    ) -> list[Preset]:
        """List non-deleted presets ordered by id, starting after `after` if given."""
        ...
