from typing import TYPE_CHECKING

from sqlalchemy import select

from app.modules.graph.adapters.persistence.models import EdgeTypeModel
from app.modules.graph.domain.edge_type import EdgeType
from app.shared_kernel.slug import Slug

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


def _to_domain(model: EdgeTypeModel) -> EdgeType:
    """Convert an ORM row into the domain entity."""
    return EdgeType(
        id=model.id,
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
        self._session.add(_to_model(edge_type))
        await self._session.flush()

    async def save(self, edge_type: EdgeType) -> None:
        """Persist changes to an existing edge type."""
        await self._session.merge(_to_model(edge_type))
        await self._session.flush()

    async def get(self, edge_type_id: uuid.UUID) -> EdgeType | None:
        """Return the edge type with `edge_type_id`, or None if missing or deleted."""
        model = await self._session.get(EdgeTypeModel, edge_type_id)
        if model is None or model.deleted_at is not None:
            return None
        return _to_domain(model)

    async def get_by_slug(self, slug: str) -> EdgeType | None:
        """Return the edge type with `slug`, or None if missing or deleted."""
        stmt = (
            select(EdgeTypeModel)
            .where(EdgeTypeModel.slug == slug)
            .where(EdgeTypeModel.deleted_at.is_(None))
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return _to_domain(model) if model else None

    async def list(self, *, after: uuid.UUID | None, limit: int) -> list[EdgeType]:
        """List non-deleted edge types ordered by id, starting after `after`."""
        stmt = (
            select(EdgeTypeModel)
            .where(EdgeTypeModel.deleted_at.is_(None))
            .order_by(EdgeTypeModel.id)
            .limit(limit)
        )
        if after is not None:
            stmt = stmt.where(EdgeTypeModel.id > after)
        result = await self._session.execute(stmt)
        return [_to_domain(model) for model in result.scalars()]
