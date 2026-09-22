from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select

from app.modules.presets.adapters.persistence.models import PresetModel
from app.modules.presets.domain.preset import Preset

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


def _to_domain(model: PresetModel) -> Preset:
    """Convert an ORM row into the domain entity."""
    return Preset(
        id=model.id,
        kind=model.kind,
        label=model.label,
        description=model.description,
        definition=model.definition,
        version=model.version,
        builtin=model.builtin,
        created_at=model.created_at,
        updated_at=model.updated_at,
        deleted_at=model.deleted_at,
    )


def _to_model(preset: Preset) -> PresetModel:
    """Convert a domain entity into its ORM row."""
    return PresetModel(
        id=preset.id,
        kind=preset.kind,
        label=preset.label,
        description=preset.description,
        definition=preset.definition,
        version=preset.version,
        builtin=preset.builtin,
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

    async def get(self, preset_id: uuid.UUID) -> Preset | None:
        """Return the preset with `preset_id`, or `None` if missing or deleted."""
        logger.debug("fetching preset", preset_id=preset_id)
        model = await self._session.get(PresetModel, preset_id)
        if model is None or model.deleted_at is not None:
            return None
        return _to_domain(model)

    async def list(
        self,
        *,
        after: uuid.UUID | None,
        limit: int,
        kind: str | None = None,
        q: str | None = None,
    ) -> list[Preset]:
        """List non-deleted presets ordered by id, starting after `after` if given."""
        logger.debug("listing presets", after=after, limit=limit, kind=kind)
        stmt = (
            select(PresetModel)
            .where(PresetModel.deleted_at.is_(None))
            .order_by(PresetModel.id)
            .limit(limit)
        )
        if kind is not None:
            stmt = stmt.where(PresetModel.kind == kind)
        if after is not None:
            stmt = stmt.where(PresetModel.id > after)
        if q is not None:
            stmt = stmt.where(PresetModel.label.ilike(f"%{q}%"))
        result = await self._session.execute(stmt)
        return [_to_domain(model) for model in result.scalars()]
