from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import builtins
    import uuid
    from datetime import datetime

    from app.modules.presets.domain.preset import Preset


class InMemoryPresetRepository:
    """Dict-backed `PresetRepository` for tests and the in-memory adapter."""

    def __init__(self) -> None:
        self._presets: dict[uuid.UUID, Preset] = {}

    async def add(self, preset: Preset) -> None:
        """Add a new preset."""
        self._presets[preset.id] = preset

    async def save(self, preset: Preset) -> None:
        """Persist changes to an existing preset."""
        self._presets[preset.id] = preset

    async def get(self, preset_id: uuid.UUID) -> Preset | None:
        """Return the preset with `preset_id`, or `None` if missing or deleted."""
        preset = self._presets.get(preset_id)
        if preset is None or preset.is_deleted:
            return None
        return preset

    async def list(
        self,
        *,
        after: uuid.UUID | None,
        limit: int,
        kind: str | None = None,
        q: str | None = None,
    ) -> list[Preset]:
        """List non-deleted presets ordered by id, starting after `after` if given."""
        ordered = sorted(
            (p for p in self._presets.values() if not p.is_deleted),
            key=lambda p: p.id,
        )
        if kind is not None:
            ordered = [p for p in ordered if p.kind == kind]
        if after is not None:
            ordered = [p for p in ordered if p.id > after]
        if q is not None:
            needle = q.casefold()
            ordered = [p for p in ordered if needle in p.label.casefold()]
        return ordered[:limit]

    async def list_deleted_before(
        self, cutoff: datetime, *, after: uuid.UUID | None, limit: int
    ) -> builtins.list[Preset]:
        """List rows soft-deleted before `cutoff`, ordered by id after `after`."""
        ordered = sorted(
            (
                p
                for p in self._presets.values()
                if p.deleted_at is not None and p.deleted_at < cutoff
            ),
            key=lambda p: p.id,
        )
        if after is not None:
            ordered = [p for p in ordered if p.id > after]
        return ordered[:limit]

    async def purge(self, preset_id: uuid.UUID) -> None:
        """Hard-delete the row, live or soft-deleted; an unknown id is a no-op."""
        self._presets.pop(preset_id, None)
