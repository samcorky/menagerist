from typing import TYPE_CHECKING

from sqlalchemy import select

from app.modules.graph.adapters.persistence.models import NodeTypeModel
from app.modules.graph.domain.node_type import NodeType
from app.shared_kernel.slug import Slug

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


def _to_domain(model: NodeTypeModel) -> NodeType:
    """Convert an ORM row into the domain entity."""
    return NodeType(
        id=model.id,
        slug=Slug(model.slug),
        label=model.label,
        description=model.description,
        attributes_schema=model.attributes_schema,
        created_at=model.created_at,
        updated_at=model.updated_at,
        deleted_at=model.deleted_at,
    )


def _to_model(node_type: NodeType) -> NodeTypeModel:
    """Convert a domain entity into its ORM row."""
    return NodeTypeModel(
        id=node_type.id,
        slug=str(node_type.slug),
        label=node_type.label,
        description=node_type.description,
        attributes_schema=node_type.attributes_schema,
        created_at=node_type.created_at,
        updated_at=node_type.updated_at,
        deleted_at=node_type.deleted_at,
    )


class SqlAlchemyNodeTypeRepository:
    """Postgres-backed `NodeTypeRepository`, scoped to a single session/transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, node_type: NodeType) -> None:
        """Add a new node type."""
        self._session.add(_to_model(node_type))
        await self._session.flush()

    async def save(self, node_type: NodeType) -> None:
        """Persist changes to an existing node type."""
        await self._session.merge(_to_model(node_type))
        await self._session.flush()

    async def get(self, node_type_id: uuid.UUID) -> NodeType | None:
        """Return the node type with `node_type_id`, or `None` if missing or deleted."""
        model = await self._session.get(NodeTypeModel, node_type_id)
        if model is None or model.deleted_at is not None:
            return None
        return _to_domain(model)

    async def get_by_slug(self, slug: str) -> NodeType | None:
        """Return the node type with `slug`, or `None` if missing or deleted."""
        stmt = (
            select(NodeTypeModel)
            .where(NodeTypeModel.slug == slug)
            .where(NodeTypeModel.deleted_at.is_(None))
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return _to_domain(model) if model else None

    async def list(self, *, after: uuid.UUID | None, limit: int) -> list[NodeType]:
        """List non-deleted node types ordered by id, starting after `after`."""
        stmt = (
            select(NodeTypeModel)
            .where(NodeTypeModel.deleted_at.is_(None))
            .order_by(NodeTypeModel.id)
            .limit(limit)
        )
        if after is not None:
            stmt = stmt.where(NodeTypeModel.id > after)
        result = await self._session.execute(stmt)
        return [_to_domain(model) for model in result.scalars()]
