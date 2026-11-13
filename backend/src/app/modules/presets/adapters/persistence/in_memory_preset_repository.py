from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import builtins
    import uuid
    from datetime import datetime

    from app.modules.presets.domain.preset import Preset
    from app.shared_kernel.content_filter import ContentFilter


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

    async def get(self, preset_id: uuid.UUID, *, scope: ContentFilter) -> Preset | None:
        """Return the preset, or `None` if missing, deleted or outside `scope`."""
        preset = self._presets.get(preset_id)
        if preset is None or preset.is_deleted or not scope.covers(preset.owner_id):
            return None
        return preset

    async def list(
        self,
        *,
        scope: ContentFilter,
        after: uuid.UUID | None,
        limit: int,
        kind: str | None = None,
        q: str | None = None,
    ) -> list[Preset]:
        """List non-deleted presets in `scope` ordered by id, after `after` if given."""
        ordered = sorted(
            (
                p
                for p in self._presets.values()
                if not p.is_deleted and scope.covers(p.owner_id)
            ),
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

    async def claim_orphaned(
        self, owner_id: uuid.UUID, *, legacy_owner_ids: frozenset[uuid.UUID]
    ) -> int:
        """Give `owner_id` every preset with no owner or a legacy owner."""
        claimed = [
            row
            for row in self._presets.values()
            if row.owner_id is None or row.owner_id in legacy_owner_ids
        ]
        for row in claimed:
            row.owner_id = owner_id
        return len(claimed)
