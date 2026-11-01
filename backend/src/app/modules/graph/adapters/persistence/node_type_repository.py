from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select

from app.modules.graph.adapters.persistence.models import NodeTypeModel
from app.modules.graph.domain.node_type import NodeType
from app.shared_kernel.slug import Slug

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


def _to_domain(model: NodeTypeModel) -> NodeType:
    """Convert an ORM row into the domain entity."""
    return NodeType(
        id=model.id,
        slug=Slug(model.slug),
        label=model.label,
        description=model.description,
        attributes_schema=model.attributes_schema,
        icon=model.icon,
        colour=model.colour,
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
        icon=node_type.icon,
        colour=node_type.colour,
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
        logger.debug("adding node type", node_type_id=node_type.id)
        self._session.add(_to_model(node_type))
        await self._session.flush()

    async def save(self, node_type: NodeType) -> None:
        """Persist changes to an existing node type."""
        logger.debug("saving node type", node_type_id=node_type.id)
        await self._session.merge(_to_model(node_type))
        await self._session.flush()

    async def get(self, node_type_id: uuid.UUID) -> NodeType | None:
        """Return the node type with `node_type_id`, or `None` if missing or deleted."""
        logger.debug("fetching node type", node_type_id=node_type_id)
        model = await self._session.get(NodeTypeModel, node_type_id)
        if model is None or model.deleted_at is not None:
            return None
        return _to_domain(model)

    async def get_for_removal(self, node_type_id: uuid.UUID) -> NodeType | None:
        """Like `get`, but take an exclusive row lock until the transaction ends."""
        stmt = (
            select(NodeTypeModel)
            .where(NodeTypeModel.id == node_type_id)
            .where(NodeTypeModel.deleted_at.is_(None))
            .with_for_update()
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_domain(model) if model else None

    async def get_by_slug(
        self, slug: str, *, guard_item_write: bool = False
    ) -> NodeType | None:
        """Return the node type with `slug`, or `None` if missing or deleted.

        `guard_item_write` takes a key-share row lock: it conflicts only with the
        exclusive lock in `get_for_removal`, never with ordinary type edits.
        """
        logger.debug("fetching node type by slug", slug=slug)
        stmt = (
            select(NodeTypeModel)
            .where(NodeTypeModel.slug == slug)
            .where(NodeTypeModel.deleted_at.is_(None))
        )
        if guard_item_write:
            stmt = stmt.with_for_update(key_share=True)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return _to_domain(model) if model else None

    async def list(self, *, after: uuid.UUID | None, limit: int) -> list[NodeType]:
        """List non-deleted node types ordered by id, starting after `after`."""
        logger.debug("listing node types", after=after, limit=limit)
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
