from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import builtins
    import uuid
    from datetime import datetime

    from app.modules.presets.domain.preset import Preset
    from app.shared_kernel.content_filter import ContentFilter
    from app.shared_kernel.paging import Page, PageRequest


class PresetRepository(Protocol):
    """Access to preset, independent of storage backend."""

    async def add(self, preset: Preset) -> None:
        """Add a new preset."""
        ...

    async def save(self, preset: Preset) -> None:
        """Persist changes to an existing preset."""
        ...

    async def get(self, preset_id: uuid.UUID, *, scope: ContentFilter) -> Preset | None:
        """Return the preset, or `None` if missing, deleted or outside `scope`."""
        ...

    async def list(
        self,
        *,
        scope: ContentFilter,
        page: PageRequest,
        kind: str | None = None,
        q: str | None = None,
    ) -> Page[Preset]:
        """List non-deleted presets in `scope`, one page in the order `page` asks.

        The sort keys are `label` (ignoring case), `kind`, `created_at` and
        `updated_at`; with none, the order is by id. A `q` keeps presets whose label
        contains it, ignoring case and accents.

        Raises:
            InvalidCursorError: `page.after` is from a different sort or order.
        """
        ...

    async def list_deleted_before(
        self, cutoff: datetime, *, after: uuid.UUID | None, limit: int
    ) -> builtins.list[Preset]:
        """List presets soft-deleted before `cutoff`, ordered by id after `after`.

        System-level, for the retention purge.
        """
        ...

    async def purge(self, preset_id: uuid.UUID) -> None:
        """Hard-delete the row, live or soft-deleted; an unknown id is a no-op."""
        ...

    async def claim_orphaned(
        self, owner_id: uuid.UUID, *, legacy_owner_ids: frozenset[uuid.UUID]
    ) -> int:
        """Give `owner_id` every preset with no owner or a legacy owner.

        System-level, for the first-admin claim; returns the number changed.
        """
        ...
