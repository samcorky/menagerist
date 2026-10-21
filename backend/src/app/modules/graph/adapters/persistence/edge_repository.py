from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import and_, column, exists, func, literal, or_, select
from sqlalchemy.dialects.postgresql import JSONB

from app.modules.graph.adapters.persistence.models import EdgeModel
from app.modules.graph.domain.edge import Edge
from app.platform.orm_mixins import claim_rows, owned_by

if TYPE_CHECKING:
    import builtins
    import uuid

    from sqlalchemy import ColumnElement, SQLColumnExpression
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.shared_kernel.content_filter import ContentFilter

logger = structlog.get_logger()


def _has_matching_row(
    attributes: SQLColumnExpression[Any], key: str, sub_key: str, value: str | None
) -> ColumnElement[bool]:
    """Whether any row of group array `key` holds `sub_key`, optionally == `value`."""
    elements = func.jsonb_array_elements(attributes[key]).table_valued(
        column("value", JSONB), name="elem"
    )
    row = elements.c.value
    conditions = [row.has_key(sub_key)]
    if value is not None:
        conditions.append(row.contains({sub_key: value}))
    return exists(select(literal(1)).select_from(elements).where(*conditions))


def _to_domain(model: EdgeModel) -> Edge:
    """Convert an ORM row into the domain entity."""
    return Edge(
        id=model.id,
        owner_id=model.owner_id,
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
        owner_id=edge.owner_id,
        source_id=edge.source_id,
        target_id=edge.target_id,
        type=edge.type,
        attributes=edge.attributes,
        created_at=edge.created_at,
        updated_at=edge.updated_at,
        deleted_at=edge.deleted_at,
    )


def _in_scope(scope: ContentFilter) -> ColumnElement[bool]:
    """The one visibility predicate: live edges the `scope` covers.

    Edges with no owner are visible only under `everyone()`.
    """
    return and_(EdgeModel.deleted_at.is_(None), owned_by(EdgeModel, scope.user_id))


class SqlAlchemyEdgeRepository:
    """Postgres-backed `EdgeRepository`, scoped to a single session/transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, edge: Edge) -> None:
        """Add a new edge.

        Flushes immediately for the same reason `SqlAlchemyNodeRepository.add`
        does - keeps later reads/writes in the same unit of work consistent.
        """
        logger.debug("adding edge", edge_id=edge.id)
        self._session.add(_to_model(edge))
        await self._session.flush()

    async def save(self, edge: Edge) -> None:
        """Persist changes to an existing edge."""
        logger.debug("saving edge", edge_id=edge.id)
        await self._session.merge(_to_model(edge))
        await self._session.flush()

    async def get(self, edge_id: uuid.UUID, *, scope: ContentFilter) -> Edge | None:
        """Return the edge with `edge_id`, or `None` if missing, deleted or unseen."""
        logger.debug("fetching edge", edge_id=edge_id)
        result = await self._session.execute(
            select(EdgeModel).where(_in_scope(scope), EdgeModel.id == edge_id)
        )
        model = result.scalar_one_or_none()
        return None if model is None else _to_domain(model)

    async def list_for_node(
        self,
        node_id: uuid.UUID,
        *,
        scope: ContentFilter,
        after: uuid.UUID | None,
        limit: int,
    ) -> list[Edge]:
        """List non-deleted edge where `node_id` is the source or target."""
        logger.debug("listing edges for node", node_id=node_id)
        stmt = (
            select(EdgeModel)
            .where(
                _in_scope(scope),
                or_(EdgeModel.source_id == node_id, EdgeModel.target_id == node_id),
            )
            .order_by(EdgeModel.id)
            .limit(limit)
        )
        if after is not None:
            stmt = stmt.where(EdgeModel.id > after)
        result = await self._session.execute(stmt)
        return [_to_domain(model) for model in result.scalars()]

    async def list(
        self, *, scope: ContentFilter, after: uuid.UUID | None, limit: int
    ) -> list[Edge]:
        """List non-deleted edge ordered by id, starting after `after` if given."""
        logger.debug("listing edges", after=after, limit=limit)
        stmt = (
            select(EdgeModel)
            .where(_in_scope(scope))
            .order_by(EdgeModel.id)
            .limit(limit)
        )
        if after is not None:
            stmt = stmt.where(EdgeModel.id > after)
        result = await self._session.execute(stmt)
        return [_to_domain(model) for model in result.scalars()]

    async def has_edges_of_type(self, type_slug: str, *, scope: ContentFilter) -> bool:
        """Return True if any non-deleted edges reference `type_slug`."""
        logger.debug("checking edges of type", type_slug=type_slug)
        stmt = select(exists().where(_in_scope(scope), EdgeModel.type == type_slug))
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def count_with_attribute(
        self,
        type_slug: str,
        key: str,
        *,
        scope: ContentFilter,
        sub_key: str | None = None,
        value: str | None = None,
    ) -> int:
        """Count non-deleted edges of `type_slug` whose attributes contain `key`."""
        logger.debug("counting edges with attribute", type_slug=type_slug, key=key)
        stmt = (
            select(func.count())
            .select_from(EdgeModel)
            .where(_in_scope(scope), EdgeModel.type == type_slug)
        )
        if sub_key is None:
            stmt = stmt.where(EdgeModel.attributes.has_key(key))
            if value is not None:
                # A string value, or a multiple-choice array holding it.
                stmt = stmt.where(
                    or_(
                        EdgeModel.attributes.contains({key: value}),
                        EdgeModel.attributes.contains({key: [value]}),
                    )
                )
        else:
            stmt = stmt.where(
                _has_matching_row(EdgeModel.attributes, key, sub_key, value)
            )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def list_with_attribute(
        self,
        type_slug: str,
        key: str,
        *,
        scope: ContentFilter,
        sub_key: str | None = None,
        after: uuid.UUID | None,
        limit: int,
    ) -> builtins.list[Edge]:
        """List non-deleted edges of `type_slug` holding `key`, ordered by id."""
        logger.debug("listing edges with attribute", type_slug=type_slug, key=key)
        stmt = select(EdgeModel).where(_in_scope(scope), EdgeModel.type == type_slug)
        if sub_key is None:
            stmt = stmt.where(EdgeModel.attributes.has_key(key))
        else:
            stmt = stmt.where(
                _has_matching_row(EdgeModel.attributes, key, sub_key, None)
            )
        stmt = stmt.order_by(EdgeModel.id).limit(limit)
        if after is not None:
            stmt = stmt.where(EdgeModel.id > after)
        result = await self._session.execute(stmt)
        return [_to_domain(model) for model in result.scalars()]

    async def claim_orphaned(
        self, owner_id: uuid.UUID, *, legacy_owner_ids: frozenset[uuid.UUID]
    ) -> int:
        """Give `owner_id` every connection with no owner or a legacy owner."""
        return await claim_rows(self._session, EdgeModel, owner_id, legacy_owner_ids)
