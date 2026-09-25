from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import (
    ARRAY,
    Text,
    and_,
    bindparam,
    column,
    exists,
    func,
    literal,
    literal_column,
    or_,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.modules.graph.adapters.persistence.models import NodeModel
from app.modules.graph.domain.node import Node

if TYPE_CHECKING:
    import builtins
    import uuid
    from collections.abc import Mapping, Sequence

    from sqlalchemy import ColumnElement, SQLColumnExpression
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


def _to_domain(model: NodeModel) -> Node:
    """Convert an ORM row into the domain entity."""
    return Node(
        id=model.id,
        name=model.name,
        type=model.type,
        description=model.description,
        attributes=model.attributes,
        favourite=model.favourite,
        tags=model.tags,
        extra_schema=model.extra_schema,
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
        favourite=node.favourite,
        tags=node.tags,
        extra_schema=node.extra_schema,
        created_at=node.created_at,
        updated_at=node.updated_at,
        deleted_at=node.deleted_at,
    )


_LIKE_ESCAPE = "\\"


def _like_pattern(q: str) -> str:
    """Return a contains-pattern for `q` with LIKE wildcards escaped."""
    escaped = q.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
    escaped = escaped.replace("%", _LIKE_ESCAPE + "%").replace("_", _LIKE_ESCAPE + "_")
    return f"%{escaped}%"


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


def _has_matching_value(
    attributes: SQLColumnExpression[Any], pattern: str
) -> ColumnElement[bool]:
    """Whether any string or number anywhere inside `attributes` matches `pattern`.

    Walks every nested value; key names, booleans and nulls never match.
    """
    value = func.jsonb_path_query(
        attributes, literal_column("'strict $.**'")
    ).column_valued("v")
    text_value = value.op("#>>")(literal_column("'{}'"))
    return exists(
        select(literal(1)).where(
            func.jsonb_typeof(value).in_(("string", "number")),
            text_value.ilike(pattern, escape=_LIKE_ESCAPE),
        )
    )


def _search_clause(
    q: str, exclusions: Mapping[str, Sequence[str]] | None
) -> ColumnElement[bool]:
    """Match `q` against name, description and attribute values, per type exclusions."""
    pattern = _like_pattern(q)
    attributes = NodeModel.attributes
    excluded = {slug: list(keys) for slug, keys in (exclusions or {}).items() if keys}
    scans = [
        and_(
            NodeModel.type == slug,
            _has_matching_value(
                attributes.op("-")(bindparam(f"excl_{i}", keys, type_=ARRAY(Text))),
                pattern,
            ),
        )
        for i, (slug, keys) in enumerate(excluded.items())
    ]
    unrestricted = _has_matching_value(attributes, pattern)
    if excluded:
        unrestricted = and_(
            or_(NodeModel.type.is_(None), NodeModel.type.not_in(list(excluded))),
            unrestricted,
        )
    return (
        NodeModel.name.ilike(pattern, escape=_LIKE_ESCAPE)
        | NodeModel.description.ilike(pattern, escape=_LIKE_ESCAPE)
        | or_(*scans, unrestricted)
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
        logger.debug("adding node", node_id=node.id)
        self._session.add(_to_model(node))
        await self._session.flush()

    async def save(self, node: Node) -> None:
        """Persist changes to an existing node."""
        logger.debug("saving node", node_id=node.id)
        await self._session.merge(_to_model(node))
        await self._session.flush()

    async def get(self, node_id: uuid.UUID) -> Node | None:
        """Return the node with `node_id`, or `None` if missing or deleted."""
        logger.debug("fetching node", node_id=node_id)
        model = await self._session.get(NodeModel, node_id)
        if model is None or model.deleted_at is not None:
            return None
        return _to_domain(model)

    async def list(
        self,
        *,
        after: uuid.UUID | None,
        limit: int,
        type: str | None = None,
        q: str | None = None,
        favourite: bool | None = None,
        attribute_search_exclusions: Mapping[str, Sequence[str]] | None = None,
    ) -> list[Node]:
        """List non-deleted node ordered by id, starting after `after` if given."""
        logger.debug("listing nodes", after=after, limit=limit, type=type)
        stmt = (
            select(NodeModel)
            .where(NodeModel.deleted_at.is_(None))
            .order_by(NodeModel.id)
            .limit(limit)
        )
        if type is not None:
            stmt = stmt.where(NodeModel.type == type)
        if after is not None:
            stmt = stmt.where(NodeModel.id > after)
        if q is not None:
            stmt = stmt.where(_search_clause(q, attribute_search_exclusions))
        if favourite is not None:
            stmt = stmt.where(NodeModel.favourite == favourite)
        result = await self._session.execute(stmt)
        return [_to_domain(model) for model in result.scalars()]

    async def count(
        self,
        *,
        type: str | None = None,
        q: str | None = None,
        favourite: bool | None = None,
        attribute_search_exclusions: Mapping[str, Sequence[str]] | None = None,
    ) -> int:
        """Return the total number of non-deleted nodes matching the given filters."""
        logger.debug("counting nodes", type=type)
        stmt = (
            select(func.count())
            .select_from(NodeModel)
            .where(NodeModel.deleted_at.is_(None))
        )
        if type is not None:
            stmt = stmt.where(NodeModel.type == type)
        if q is not None:
            stmt = stmt.where(_search_clause(q, attribute_search_exclusions))
        if favourite is not None:
            stmt = stmt.where(NodeModel.favourite == favourite)
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def clear_type(self, type_slug: str) -> None:
        """Set `type` to NULL on all non-deleted nodes if type matches `type_slug`."""
        logger.debug("clearing node type", type_slug=type_slug)
        stmt = (
            update(NodeModel)
            .where(NodeModel.deleted_at.is_(None), NodeModel.type == type_slug)
            .values(type=None)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def count_with_attribute(
        self,
        type_slug: str,
        key: str,
        *,
        sub_key: str | None = None,
        value: str | None = None,
    ) -> int:
        """Count non-deleted nodes of `type_slug` whose attributes contain `key`."""
        logger.debug("counting nodes with attribute", type_slug=type_slug, key=key)
        stmt = (
            select(func.count())
            .select_from(NodeModel)
            .where(NodeModel.deleted_at.is_(None), NodeModel.type == type_slug)
        )
        if sub_key is None:
            stmt = stmt.where(NodeModel.attributes.has_key(key))
            if value is not None:
                stmt = stmt.where(NodeModel.attributes.contains({key: value}))
        else:
            stmt = stmt.where(
                _has_matching_row(NodeModel.attributes, key, sub_key, value)
            )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def list_with_attribute(
        self,
        type_slug: str,
        key: str,
        *,
        sub_key: str | None = None,
        after: uuid.UUID | None,
        limit: int,
    ) -> builtins.list[Node]:
        """List non-deleted nodes of `type_slug` holding `key`, ordered by id."""
        logger.debug("listing nodes with attribute", type_slug=type_slug, key=key)
        stmt = select(NodeModel).where(
            NodeModel.deleted_at.is_(None), NodeModel.type == type_slug
        )
        if sub_key is None:
            stmt = stmt.where(NodeModel.attributes.has_key(key))
        else:
            stmt = stmt.where(
                _has_matching_row(NodeModel.attributes, key, sub_key, None)
            )
        stmt = stmt.order_by(NodeModel.id).limit(limit)
        if after is not None:
            stmt = stmt.where(NodeModel.id > after)
        result = await self._session.execute(stmt)
        return [_to_domain(model) for model in result.scalars()]
