from typing import TYPE_CHECKING

from sqlalchemy import or_, select

from app.modules.graph.adapters.persistence.models import EdgeModel
from app.modules.graph.domain.edge import Edge

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


def _to_domain(model: EdgeModel) -> Edge:
    """Convert an ORM row into the domain entity."""
    return Edge(
        id=model.id,
        source_id=model.source_id,
        target_id=model.target_id,
        type=model.type,
        attributes=model.attributes,
        created_at=model.created_at,
        updated_at=model.updated_at,
        deleted_at=model.deleted_at,
    )


def _to_model(edge: Edge) -> EdgeModel:
    """Convert a domain entity into its ORM row."""
    return EdgeModel(
        id=edge.id,
        source_id=edge.source_id,
        target_id=edge.target_id,
        type=edge.type,
        attributes=edge.attributes,
        created_at=edge.created_at,
        updated_at=edge.updated_at,
        deleted_at=edge.deleted_at,
    )


class SqlAlchemyEdgeRepository:
    """Postgres-backed `EdgeRepository`, scoped to a single session/transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, edge: Edge) -> None:
        """Add a new edge.

        Flushes immediately for the same reason `SqlAlchemyNodeRepository.add`
        does - keeps later reads/writes in the same unit of work consistent.
        """
        self._session.add(_to_model(edge))
        await self._session.flush()

    async def save(self, edge: Edge) -> None:
        """Persist changes to an existing edge."""
        await self._session.merge(_to_model(edge))
        await self._session.flush()

    async def get(self, edge_id: uuid.UUID) -> Edge | None:
        """Return the edge with `edge_id`, or `None` if missing or deleted."""
        model = await self._session.get(EdgeModel, edge_id)
        if model is None or model.deleted_at is not None:
            return None
        return _to_domain(model)

    async def list_for_node(
        self, node_id: uuid.UUID, *, after: uuid.UUID | None, limit: int
    ) -> list[Edge]:
        """List non-deleted edges where `node_id` is the source or target."""
        stmt = (
            select(EdgeModel)
            .where(
                EdgeModel.deleted_at.is_(None),
                or_(EdgeModel.source_id == node_id, EdgeModel.target_id == node_id),
            )
            .order_by(EdgeModel.id)
            .limit(limit)
        )
        if after is not None:
            stmt = stmt.where(EdgeModel.id > after)
        result = await self._session.execute(stmt)
        return [_to_domain(model) for model in result.scalars()]

    async def list(self, *, after: uuid.UUID | None, limit: int) -> list[Edge]:
        """List non-deleted edges ordered by id, starting after `after` if given."""
        stmt = (
            select(EdgeModel)
            .where(EdgeModel.deleted_at.is_(None))
            .order_by(EdgeModel.id)
            .limit(limit)
        )
        if after is not None:
            stmt = stmt.where(EdgeModel.id > after)
        result = await self._session.execute(stmt)
        return [_to_domain(model) for model in result.scalars()]
