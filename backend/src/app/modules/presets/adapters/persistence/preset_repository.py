from typing import TYPE_CHECKING

import structlog
from sqlalchemy import delete, select

from app.modules.presets.adapters.persistence.models import PresetModel
from app.modules.presets.domain.preset import Preset
from app.platform.keyset import keyset_page, text_column, timestamp_column
from app.platform.orm_mixins import claim_rows, owned_by
from app.platform.text_search import contains_pattern, unaccent_ilike

if TYPE_CHECKING:
    import builtins
    import uuid
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.shared_kernel.content_filter import ContentFilter
    from app.shared_kernel.paging import Page, PageRequest

logger = structlog.get_logger()

# What `list` can sort by; the names are fields of the API's preset response.
_SORT_COLUMNS = {
    "label": text_column(PresetModel.label),
    "kind": text_column(PresetModel.kind),
    "created_at": timestamp_column(PresetModel.created_at),
    "updated_at": timestamp_column(PresetModel.updated_at),
}


def _to_domain(model: PresetModel) -> Preset:
    """Convert an ORM row into the domain entity."""
    return Preset(
        id=model.id,
        owner_id=model.owner_id,
        kind=model.kind,
        label=model.label,
        description=model.description,
        definition=model.definition,
        version=model.version,
        created_at=model.created_at,
        updated_at=model.updated_at,
        deleted_at=model.deleted_at,
    )


def _to_model(preset: Preset) -> PresetModel:
    """Convert a domain entity into its ORM row."""
    return PresetModel(
        id=preset.id,
        owner_id=preset.owner_id,
        kind=preset.kind,
        label=preset.label,
        description=preset.description,
        definition=preset.definition,
        version=preset.version,
        created_at=preset.created_at,
        updated_at=preset.updated_at,
        deleted_at=preset.deleted_at,
    )


class SqlAlchemyPresetRepository:
    """Postgres-backed `PresetRepository`, scoped to a single session/transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, preset: Preset) -> None:
        """Add a new preset."""
        logger.debug("adding preset", preset_id=preset.id)
        self._session.add(_to_model(preset))
        await self._session.flush()

    async def save(self, preset: Preset) -> None:
        """Persist changes to an existing preset."""
        logger.debug("saving preset", preset_id=preset.id)
        await self._session.merge(_to_model(preset))
        await self._session.flush()

    async def get(self, preset_id: uuid.UUID, *, scope: ContentFilter) -> Preset | None:
        """Return the preset, or `None` if missing, deleted or outside `scope`."""
        logger.debug("fetching preset", preset_id=preset_id)
        stmt = select(PresetModel).where(
            PresetModel.id == preset_id,
            PresetModel.deleted_at.is_(None),
            owned_by(PresetModel, scope.user_id),
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_domain(model) if model else None

    async def list(
        self,
        *,
        scope: ContentFilter,
        page: PageRequest,
        kind: str | None = None,
        q: str | None = None,
    ) -> Page[Preset]:
        """List non-deleted presets in `scope`, one page in the order `page` asks."""
        logger.debug("listing presets", page=page, kind=kind)
        stmt = (
            select(PresetModel)
            .where(PresetModel.deleted_at.is_(None))
            .where(owned_by(PresetModel, scope.user_id))
        )
        if kind is not None:
            stmt = stmt.where(PresetModel.kind == kind)
        needle = (q or "").strip()
        if needle:
            stmt = stmt.where(
                unaccent_ilike(PresetModel.label, contains_pattern(needle))
            )
        return await keyset_page(
            self._session,
            stmt,
            id_column=PresetModel.id,
            columns=_SORT_COLUMNS,
            request=page,
            to_domain=_to_domain,
            with_total=True,
        )

    async def list_deleted_before(
        self, cutoff: datetime, *, after: uuid.UUID | None, limit: int
    ) -> builtins.list[Preset]:
        """List presets soft-deleted before `cutoff`, ordered by id after `after`."""
        stmt = (
            select(PresetModel)
            .where(PresetModel.deleted_at < cutoff)
            .order_by(PresetModel.id)
            .limit(limit)
        )
        if after is not None:
            stmt = stmt.where(PresetModel.id > after)
        result = await self._session.execute(stmt)
        return [_to_domain(model) for model in result.scalars()]

    async def purge(self, preset_id: uuid.UUID) -> None:
        """Hard-delete the row, live or soft-deleted; an unknown id is a no-op."""
        await self._session.execute(
            delete(PresetModel).where(PresetModel.id == preset_id)
        )
        await self._session.flush()

    async def claim_orphaned(
        self, owner_id: uuid.UUID, *, legacy_owner_ids: frozenset[uuid.UUID]
    ) -> int:
        """Give `owner_id` every preset with no owner or a legacy owner."""
        return await claim_rows(self._session, PresetModel, owner_id, legacy_owner_ids)
