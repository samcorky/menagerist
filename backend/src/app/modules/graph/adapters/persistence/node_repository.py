from typing import TYPE_CHECKING

from sqlalchemy import select

from app.modules.graph.adapters.persistence.models import NodeModel
from app.modules.graph.domain.node import Node

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


def _to_domain(model: NodeModel) -> Node:
    """Convert an ORM row into the domain entity."""
    return Node(
        id=model.id,
        name=model.name,
        type=model.type,
        description=model.description,
        attributes=model.attributes,
        created_at=model.created_at,
        updated_at=model.updated_at,
        deleted_at=model.deleted_at,
    )


def _to_model(node: Node) -> NodeModel:
    """Convert a domain entity into its ORM row."""
    return NodeModel(
        id=node.id,
        name=node.name,
        type=node.type,
        description=node.description,
        attributes=node.attributes,
        created_at=node.created_at,
        updated_at=node.updated_at,
        deleted_at=node.deleted_at,
    )


class SqlAlchemyNodeRepository:
    """Postgres-backed `NodeRepository`, scoped to a single session/transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, node: Node) -> None:
        """Add a new node.

        Flushes immediately so the row is visible to later reads/writes within
        the same unit of work - e.g. an edge referencing this node's id,
        inserted later in the same transaction.
        """
        self._session.add(_to_model(node))
        await self._session.flush()

    async def save(self, node: Node) -> None:
        """Persist changes to an existing node."""
        await self._session.merge(_to_model(node))
        await self._session.flush()

    async def get(self, node_id: uuid.UUID) -> Node | None:
        """Return the node with `node_id`, or `None` if missing or deleted."""
        model = await self._session.get(NodeModel, node_id)
        if model is None or model.deleted_at is not None:
            return None
        return _to_domain(model)

    async def list(self, *, after: uuid.UUID | None, limit: int) -> list[Node]:
        """List non-deleted node ordered by id, starting after `after` if given."""
        stmt = (
            select(NodeModel)
            .where(NodeModel.deleted_at.is_(None))
            .order_by(NodeModel.id)
            .limit(limit)
        )
        if after is not None:
            stmt = stmt.where(NodeModel.id > after)
        result = await self._session.execute(stmt)
        return [_to_domain(model) for model in result.scalars()]
