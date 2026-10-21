from typing import TYPE_CHECKING

import structlog
from sqlalchemy import (
    Text,
    and_,
    case,
    cast,
    column,
    func,
    literal,
    or_,
    select,
    text,
    true,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB, aggregate_order_by

from app.modules.graph.adapters.persistence.models import NodeModel
from app.modules.graph.adapters.persistence.query_sql import (
    after_clause,
    compile_where,
    order_by,
    sort_expressions,
)
from app.modules.graph.adapters.persistence.search_sql import (
    has_matching_row,
    like_pattern,
    search_clause,
    unaccent_ilike,
)
from app.modules.graph.application.field_kinds import KIND_OPERATORS
from app.modules.graph.application.schema_meta import NAMESPACE
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.query import (
    ItemFieldUse,
    SearchHit,
    TextCondition,
    walk_conditions,
)
from app.platform.orm_mixins import claim_rows, owned_by

if TYPE_CHECKING:
    import builtins
    import collections.abc
    import uuid
    from collections.abc import Mapping, Sequence

    from sqlalchemy import ColumnElement
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.graph.domain.query import Cursor, ResolvedQuery
    from app.shared_kernel.content_filter import ContentFilter

logger = structlog.get_logger()


def _to_domain(model: NodeModel) -> Node:
    """Convert an ORM row into the domain entity."""
    return Node(
        id=model.id,
        owner_id=model.owner_id,
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
        owner_id=node.owner_id,
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


def _in_scope(scope: ContentFilter) -> ColumnElement[bool]:
    """The one visibility predicate: live rows the `scope` covers.

    Rows with no owner are visible only under `everyone()`.
    """
    return and_(NodeModel.deleted_at.is_(None), owned_by(NodeModel, scope.user_id))


def _has_text(resolved: ResolvedQuery) -> bool:
    return any(
        isinstance(c, TextCondition) for _, c in walk_conditions(resolved.query.where)
    )


async def _jit_off_for_text(session: AsyncSession, *, has_text: bool) -> None:
    """Turn JIT off for the rest of the transaction when a text search runs.

    JIT over-compiles plans holding the `jsonb_path_query` subplan: about 0.8 s
    extra at 100k items, while the query itself runs in 60 to 130 ms.
    """
    if has_text:
        await session.execute(text("SET LOCAL jit = off"))


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

    async def get(self, node_id: uuid.UUID, *, scope: ContentFilter) -> Node | None:
        """Return the node with `node_id`, or `None` if missing, deleted or unseen."""
        logger.debug("fetching node", node_id=node_id)
        result = await self._session.execute(
            select(NodeModel).where(_in_scope(scope), NodeModel.id == node_id)
        )
        model = result.scalar_one_or_none()
        return None if model is None else _to_domain(model)

    async def list(
        self,
        *,
        scope: ContentFilter,
        after: uuid.UUID | None,
        limit: int,
        type: str | None = None,
        q: str | None = None,
        favourite: bool | None = None,
        ids: collections.abc.Collection[uuid.UUID] | None = None,
        attribute_search_exclusions: Mapping[str, Sequence[str]] | None = None,
    ) -> list[Node]:
        """List non-deleted node ordered by id, starting after `after` if given."""
        logger.debug("listing nodes", after=after, limit=limit, type=type)
        if ids is not None and not ids:
            return []
        stmt = (
            select(NodeModel)
            .where(_in_scope(scope))
            .order_by(NodeModel.id)
            .limit(limit)
        )
        if ids is not None:
            stmt = stmt.where(NodeModel.id.in_(ids))
        if type is not None:
            stmt = stmt.where(NodeModel.type == type)
        if after is not None:
            stmt = stmt.where(NodeModel.id > after)
        if q is not None:
            stmt = stmt.where(search_clause(q, attribute_search_exclusions))
        if favourite is not None:
            stmt = stmt.where(NodeModel.favourite == favourite)
        await _jit_off_for_text(self._session, has_text=q is not None)
        result = await self._session.execute(stmt)
        return [_to_domain(model) for model in result.scalars()]

    async def search(
        self,
        *,
        scope: ContentFilter,
        resolved: ResolvedQuery,
        after: Cursor | None,
        limit: int,
    ) -> builtins.list[SearchHit]:
        """Return one page of live nodes matching the query, in its order.

        The scope is its own WHERE term, so an `or` in the query cannot widen it.
        """
        logger.debug("searching nodes", after=after, limit=limit)
        exprs = sort_expressions(resolved)
        stmt = select(NodeModel, *exprs).where(_in_scope(scope))
        where = compile_where(resolved)
        if where is not None:
            stmt = stmt.where(where)
        if after is not None:
            stmt = stmt.where(after_clause(resolved, exprs, after))
        stmt = stmt.order_by(*order_by(resolved, exprs)).limit(limit)
        await _jit_off_for_text(self._session, has_text=_has_text(resolved))
        rows = (await self._session.execute(stmt)).all()
        return [
            SearchHit(node=_to_domain(row[0]), sort_values=tuple(row[1:]))
            for row in rows
        ]

    async def search_count(
        self, *, scope: ContentFilter, resolved: ResolvedQuery, limit: int | None = None
    ) -> int:
        """Return how many live nodes in `scope` match the query.

        With `limit`, counting stops at that many matches.
        """
        logger.debug("counting search results", limit=limit)
        matches = select(NodeModel.id).where(_in_scope(scope))
        where = compile_where(resolved)
        if where is not None:
            matches = matches.where(where)
        if limit is not None:
            matches = matches.limit(limit)
        stmt = select(func.count()).select_from(matches.subquery())
        await _jit_off_for_text(self._session, has_text=_has_text(resolved))
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def count(
        self,
        *,
        scope: ContentFilter,
        type: str | None = None,
        q: str | None = None,
        favourite: bool | None = None,
        ids: collections.abc.Collection[uuid.UUID] | None = None,
        attribute_search_exclusions: Mapping[str, Sequence[str]] | None = None,
    ) -> int:
        """Return the total number of non-deleted nodes matching the given filters."""
        logger.debug("counting nodes", type=type)
        if ids is not None and not ids:
            return 0
        stmt = select(func.count()).select_from(NodeModel).where(_in_scope(scope))
        if ids is not None:
            stmt = stmt.where(NodeModel.id.in_(ids))
        if type is not None:
            stmt = stmt.where(NodeModel.type == type)
        if q is not None:
            stmt = stmt.where(search_clause(q, attribute_search_exclusions))
        if favourite is not None:
            stmt = stmt.where(NodeModel.favourite == favourite)
        await _jit_off_for_text(self._session, has_text=q is not None)
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def clear_type(self, type_slug: str, *, scope: ContentFilter) -> None:
        """Set `type` to NULL on all non-deleted nodes if type matches `type_slug`."""
        logger.debug("clearing node type", type_slug=type_slug)
        stmt = (
            update(NodeModel)
            .where(_in_scope(scope), NodeModel.type == type_slug)
            .values(type=None)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def count_with_attribute(
        self,
        type_slug: str,
        key: str,
        *,
        scope: ContentFilter,
        sub_key: str | None = None,
        value: str | None = None,
    ) -> int:
        """Count non-deleted nodes of `type_slug` whose attributes contain `key`."""
        logger.debug("counting nodes with attribute", type_slug=type_slug, key=key)
        stmt = (
            select(func.count())
            .select_from(NodeModel)
            .where(_in_scope(scope), NodeModel.type == type_slug)
        )
        if sub_key is None:
            stmt = stmt.where(NodeModel.attributes.has_key(key))
            if value is not None:
                # A string value, or a multiple-choice array holding it.
                stmt = stmt.where(
                    or_(
                        NodeModel.attributes.contains({key: value}),
                        NodeModel.attributes.contains({key: [value]}),
                    )
                )
        else:
            stmt = stmt.where(
                has_matching_row(NodeModel.attributes, key, sub_key, value)
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
    ) -> builtins.list[Node]:
        """List non-deleted nodes of `type_slug` holding `key`, ordered by id."""
        logger.debug("listing nodes with attribute", type_slug=type_slug, key=key)
        stmt = select(NodeModel).where(_in_scope(scope), NodeModel.type == type_slug)
        if sub_key is None:
            stmt = stmt.where(NodeModel.attributes.has_key(key))
        else:
            stmt = stmt.where(
                has_matching_row(NodeModel.attributes, key, sub_key, None)
            )
        stmt = stmt.order_by(NodeModel.id).limit(limit)
        if after is not None:
            stmt = stmt.where(NodeModel.id > after)
        result = await self._session.execute(stmt)
        return [_to_domain(model) for model in result.scalars()]

    async def list_attribute_values(
        self,
        type_slug: str,
        key: str,
        *,
        scope: ContentFilter,
        q: str | None = None,
        limit: int = 20,
    ) -> builtins.list[tuple[str, int]]:
        """Distinct string values of `key` on non-deleted nodes of `type_slug`."""
        logger.debug("listing attribute values", type_slug=type_slug, key=key)
        raw_value = NodeModel.attributes[key]
        value = raw_value.astext
        stmt = (
            select(value, func.count())
            .where(
                _in_scope(scope),
                NodeModel.type == type_slug,
                func.jsonb_typeof(raw_value) == "string",
            )
            .group_by(value)
        )
        if q is not None:
            stmt = stmt.where(unaccent_ilike(value, like_pattern(q)))
        stmt = stmt.order_by(func.count().desc(), value.asc()).limit(limit)
        result = await self._session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def item_fields(
        self, *, scope: ContentFilter, limit: int
    ) -> builtins.list[ItemFieldUse]:
        """List the per-item fields declared in the overlays of live nodes."""
        logger.debug("listing item fields")
        properties = NodeModel.extra_schema["properties"]
        # jsonb_each raises on a non-object, so feed it `{}` instead.
        as_object = case(
            (func.jsonb_typeof(properties) == "object", properties),
            else_=cast(literal("{}"), JSONB),
        )
        fields = (
            func.jsonb_each(as_object)
            .table_valued(column("key", Text), column("value", JSONB), name="field")
            .lateral()
        )
        meta = fields.c.value[NAMESPACE]
        kind = meta["kind"].astext
        raw_title = fields.c.value["title"]
        title = func.nullif(
            case(
                (func.jsonb_typeof(raw_title) == "string", raw_title.astext),
                else_=None,
            ),
            "",
        )
        per_title = (
            select(
                fields.c.key.label("key"),
                kind.label("kind"),
                title.label("title"),
                func.count().label("n"),
            )
            .select_from(NodeModel)
            .join(fields, true())
            .where(
                _in_scope(scope),
                kind.in_(list(KIND_OPERATORS)),
                meta["archived"].is_distinct_from(cast(literal("true"), JSONB)),
            )
            .group_by(fields.c.key, kind, title)
            .subquery()
        )
        total = func.sum(per_title.c.n)
        label = func.array_agg(
            aggregate_order_by(
                per_title.c.title, per_title.c.n.desc(), per_title.c.title
            )
        ).filter(per_title.c.title.is_not(None))
        stmt = (
            select(per_title.c.key, per_title.c.kind, total, label[1])
            .group_by(per_title.c.key, per_title.c.kind)
            .order_by(total.desc(), per_title.c.key.collate("C"), per_title.c.kind)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [
            ItemFieldUse(key=key, kind=kind_, label=name or key, count=int(count))
            for key, kind_, count, name in result.all()
        ]

    async def claim_orphaned(
        self, owner_id: uuid.UUID, *, legacy_owner_ids: frozenset[uuid.UUID]
    ) -> int:
        """Give `owner_id` every node with no owner or a legacy owner."""
        return await claim_rows(self._session, NodeModel, owner_id, legacy_owner_ids)
