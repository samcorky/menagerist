from typing import TYPE_CHECKING

import structlog
from sqlalchemy import delete, select

from app.modules.graph.adapters.persistence.models import EdgeTypeModel
from app.modules.graph.domain.edge_type import EdgeType
from app.platform.orm_mixins import claim_rows, owned_by
from app.shared_kernel.slug import Slug

if TYPE_CHECKING:
    import builtins
    import uuid
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.shared_kernel.content_filter import ContentFilter

logger = structlog.get_logger()


def _to_domain(model: EdgeTypeModel) -> EdgeType:
    """Convert an ORM row into the domain entity."""
    return EdgeType(
        id=model.id,
        owner_id=model.owner_id,
        slug=Slug(model.slug),
        label=model.label,
        reverse_label=model.reverse_label,
        description=model.description,
        directional=model.directional,
        attributes_schema=model.attributes_schema,
        created_at=model.created_at,
        updated_at=model.updated_at,
        deleted_at=model.deleted_at,
    )


def _to_model(edge_type: EdgeType) -> EdgeTypeModel:
    """Convert a domain entity into its ORM row."""
    return EdgeTypeModel(
        id=edge_type.id,
        owner_id=edge_type.owner_id,
        slug=str(edge_type.slug),
        label=edge_type.label,
        reverse_label=edge_type.reverse_label,
        description=edge_type.description,
        directional=edge_type.directional,
        attributes_schema=edge_type.attributes_schema,
        created_at=edge_type.created_at,
        updated_at=edge_type.updated_at,
        deleted_at=edge_type.deleted_at,
    )


class SqlAlchemyEdgeTypeRepository:
    """Postgres-backed EdgeTypeRepository, scoped to a single session/transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, edge_type: EdgeType) -> None:
        """Add a new edge type."""
        logger.debug("adding edge type", edge_type_id=edge_type.id)
        self._session.add(_to_model(edge_type))
        await self._session.flush()

    async def save(self, edge_type: EdgeType) -> None:
        """Persist changes to an existing edge type."""
        logger.debug("saving edge type", edge_type_id=edge_type.id)
        await self._session.merge(_to_model(edge_type))
        await self._session.flush()

    async def get(
        self, edge_type_id: uuid.UUID, *, scope: ContentFilter
    ) -> EdgeType | None:
        """Return the edge type, or None if missing, deleted or outside `scope`."""
        logger.debug("fetching edge type", edge_type_id=edge_type_id)
        stmt = select(EdgeTypeModel).where(
            EdgeTypeModel.id == edge_type_id,
            EdgeTypeModel.deleted_at.is_(None),
            owned_by(EdgeTypeModel, scope.user_id),
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_domain(model) if model else None

    async def get_by_slug(self, slug: str, *, scope: ContentFilter) -> EdgeType | None:
        """Return the edge type with `slug` in `scope`, or None if missing/deleted."""
        logger.debug("fetching edge type by slug", slug=slug)
        stmt = (
            select(EdgeTypeModel)
            .where(EdgeTypeModel.slug == slug)
            .where(EdgeTypeModel.deleted_at.is_(None))
            .where(owned_by(EdgeTypeModel, scope.user_id))
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return _to_domain(model) if model else None

    async def list(
        self, *, scope: ContentFilter, after: uuid.UUID | None, limit: int
    ) -> list[EdgeType]:
        """List non-deleted edge types in `scope` ordered by id, after `after`."""
        logger.debug("listing edge types", after=after, limit=limit)
        stmt = (
            select(EdgeTypeModel)
            .where(EdgeTypeModel.deleted_at.is_(None))
            .where(owned_by(EdgeTypeModel, scope.user_id))
            .order_by(EdgeTypeModel.id)
            .limit(limit)
        )
        if after is not None:
            stmt = stmt.where(EdgeTypeModel.id > after)
        result = await self._session.execute(stmt)
        return [_to_domain(model) for model in result.scalars()]

    async def list_deleted_before(
        self, cutoff: datetime, *, after: uuid.UUID | None, limit: int
    ) -> builtins.list[EdgeType]:
        """List relationship types deleted before `cutoff`, by id after `after`."""
        stmt = (
            select(EdgeTypeModel)
            .where(EdgeTypeModel.deleted_at < cutoff)
            .order_by(EdgeTypeModel.id)
            .limit(limit)
        )
        if after is not None:
            stmt = stmt.where(EdgeTypeModel.id > after)
        result = await self._session.execute(stmt)
        return [_to_domain(model) for model in result.scalars()]

    async def purge(self, edge_type_id: uuid.UUID) -> None:
        """Hard-delete the row, live or soft-deleted; an unknown id is a no-op."""
        await self._session.execute(
            delete(EdgeTypeModel).where(EdgeTypeModel.id == edge_type_id)
        )
        await self._session.flush()

    async def claim_orphaned(
        self, owner_id: uuid.UUID, *, legacy_owner_ids: frozenset[uuid.UUID]
    ) -> int:
        """Give `owner_id` every edge type with no owner or a legacy owner."""
        return await claim_rows(
            self._session, EdgeTypeModel, owner_id, legacy_owner_ids
        )
