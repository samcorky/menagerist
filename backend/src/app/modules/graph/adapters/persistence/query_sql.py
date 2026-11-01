"""Compile a query tree to SQLAlchemy.

`query_eval.py` is the reference: every scenario in `test_node_search.py` must
give the same answer here. Three rules keep it honest:

* every leaf is never NULL (COALESCE(..., false) where it could be), so NOT
  never sees SQL NULL;
* every cast sits inside a CASE on `jsonb_typeof`, so a value of the wrong JSON
  type yields NULL instead of an error;
* text that Python compares by code point is compared with COLLATE "C".
"""

import json
import operator
import sys
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final, Literal

from sqlalchemy import (
    Float,
    Numeric,
    Text,
    and_,
    case,
    cast,
    column,
    exists,
    false,
    func,
    literal,
    literal_column,
    not_,
    null,
    or_,
    select,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.util import ClauseAdapter

from app.modules.graph.adapters.persistence.models import EdgeModel, NodeModel
from app.modules.graph.adapters.persistence.search_sql import (
    like_pattern,
    search_clause,
    unaccent_ilike,
)
from app.modules.graph.domain.query import (
    COMPLEMENT_OPERATORS,
    CollectionCondition,
    Condition,
    ConnectionCondition,
    Cursor,
    DateCondition,
    DescriptionCondition,
    FavouriteCondition,
    FieldCondition,
    FieldReference,
    Group,
    ManualTarget,
    MediaCondition,
    Money,
    NameCondition,
    Operand,
    RelativeDate,
    ResolvedQuery,
    SmartTarget,
    SortKey,
    StaleTarget,
    TagCondition,
    TextCondition,
    TypeCondition,
)
from app.platform.orm_mixins import owned_by

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from sqlalchemy import SQLColumnExpression
    from sqlalchemy.sql.selectable import TableValuedAlias

    from app.modules.graph.adapters.persistence.query_env import QueryEnv

type _Expr = ColumnElement[Any]
type _Bool = ColumnElement[bool]

_NUMERIC: Final = frozenset({"number", "duration", "rating"})
_TEXTUAL: Final = frozenset({"text", "url", "email", "phone", "longtext"})
_C: Final = "C"  # byte-wise collation: Python's code-point string order
# Description counts as blank when only ASCII whitespace (see `description_blank`).
_BLANK_PATTERN: Final = r"^[ \t\n\r\f\v]*$"
_FLOAT_MAX: Final = Decimal(int(sys.float_info.max))


def _never_null(expression: _Bool) -> _Bool:
    return func.coalesce(expression, false())


def _typed(j: _Expr, json_type: str, value: _Expr) -> _Expr:
    """`value` when `j` holds that JSON type, else NULL."""
    return case((func.jsonb_typeof(j) == json_type, value), else_=null())


def _num(j: _Expr) -> _Expr:
    """A JSON number as float8, or NULL when it is not one or too large for one."""
    in_range = func.abs(cast(j, Numeric)) <= literal(_FLOAT_MAX, Numeric)
    # Nested CASEs: the numeric cast must only see JSON numbers.
    return _typed(j, "number", case((in_range, cast(j, Float)), else_=null()))


def _str(j: _Expr) -> _Expr:
    return _typed(j, "string", j.op("#>>", return_type=Text)(literal_column("'{}'")))


def _folded(expression: SQLColumnExpression[Any]) -> _Expr:
    return func.lower(func.immutable_unaccent(expression))


def _json(value: object) -> _Expr:
    return cast(literal(json.dumps(value)), JSONB)


def _array_or_empty(j: _Expr) -> _Expr:
    return case((func.jsonb_typeof(j) == "array", j), else_=_json([]))


def _rows(j: _Expr, name: str) -> TableValuedAlias:
    """The elements of `j` as a table, or no rows when it is not an array."""
    return func.jsonb_array_elements(_array_or_empty(j)).table_valued(
        column("value", JSONB), name=name
    )


def _any_row(rows: TableValuedAlias, *where: _Bool) -> _Bool:
    return exists(select(literal(1)).select_from(rows).where(*where))


def _is_empty(j: _Expr) -> _Bool:
    """Missing, JSON null, "" or []: never NULL itself."""
    return or_(
        j.is_(None),
        func.jsonb_typeof(j) == "null",
        j == _json(""),
        j == _json([]),
    )


_COMPARISONS: Final = {
    "=": operator.eq,
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
}


def _cmp(op: str, left: _Expr, right: Any) -> _Bool:  # noqa: ANN401
    result: _Bool = _COMPARISONS[op](left, right)
    return result


def _ordered(op: str, value: _Expr, operand: Any) -> _Bool:  # noqa: ANN401
    if op == "between":
        return and_(value >= operand[0], value <= operand[1])
    return _cmp(op, value, operand)


def _operand(operand: Operand, kind: str, ctx: ResolvedQuery) -> Any:  # noqa: ANN401
    """A bind value, or a column expression for a field reference."""
    if isinstance(operand, tuple):
        return [_operand(item, kind, ctx) for item in operand]
    if isinstance(operand, RelativeDate):
        return operand.resolve(ctx.today).isoformat()
    if isinstance(operand, FieldReference):
        other = NodeModel.attributes[operand.key]
        if kind == "money":
            return other
        return _str(other) if kind == "date" else _num(other)
    return operand


def _test_numeric(op: str, j: _Expr, operand: Any) -> _Bool:  # noqa: ANN401
    return _ordered(op, _num(j), operand)


def _money_parts(operand: Any) -> tuple[Any, Any]:  # noqa: ANN401
    """Amount and currency of a `Money` or of a referenced money field."""
    if isinstance(operand, Money):
        return operand.value, operand.currency
    return _num(operand["value"]), _str(operand["currency"])


def _test_money(op: str, j: _Expr, operand: Any) -> _Bool:  # noqa: ANN401
    amount = _num(j["value"])
    currency = _str(j["currency"])
    if op == "between":
        (low, low_currency), (high, high_currency) = map(_money_parts, operand)
        return and_(
            currency == low_currency,
            currency == high_currency,
            amount >= low,
            amount <= high,
        )
    value, value_currency = _money_parts(operand)
    return and_(currency == value_currency, _cmp(op, amount, value))


def _test_date(op: str, j: _Expr, operand: Any) -> _Bool:  # noqa: ANN401
    return _ordered(op, _str(j).collate(_C), operand)


def _test_partial_date(op: str, j: _Expr, operand: Any) -> _Bool:  # noqa: ANN401
    """Compare only as many characters as the operand gives (year, month, day)."""
    text = _str(j)

    def prefix(bound: str) -> _Expr:
        return func.left(text, len(bound)).collate(_C)

    if op == "between":
        low, high = operand
        return and_(prefix(low) >= low, prefix(high) <= high)
    return _cmp(op, prefix(operand), operand)


def _test_text(op: str, j: _Expr, operand: Any) -> _Bool:  # noqa: ANN401
    text = _str(j)
    if op == "~":
        return unaccent_ilike(text, like_pattern(operand))
    items = operand if op == "in" else [operand]
    return _folded(text).in_([_folded(literal(item)) for item in items])


def _test_choice(op: str, j: _Expr, operand: Any) -> _Bool:  # noqa: ANN401
    return _str(j).in_(operand if op == "in" else [operand])


def _test_boolean(op: str, j: _Expr, operand: Any) -> _Bool:  # noqa: ANN401
    del op
    return j == _json(operand)


def _test_multichoice(op: str, j: _Expr, operand: Any) -> _Bool:  # noqa: ANN401
    del op
    return and_(func.jsonb_typeof(j) == "array", j.contains(_json(list(operand))))


def _test_checklist(op: str, j: _Expr, operand: Any) -> _Bool:  # noqa: ANN401
    del operand
    steps = _rows(j, "step")
    step = steps.c.value
    is_object = func.jsonb_typeof(step) == "object"
    open_step = _any_row(steps, is_object, not_(step.contains(_json({"done": True}))))
    if op == "incomplete":
        return open_step
    return and_(_any_row(steps, is_object), not_(open_step))


_TESTS: Final[Mapping[str, Callable[[str, _Expr, Any], _Bool]]] = {
    **dict.fromkeys(_NUMERIC, _test_numeric),
    **dict.fromkeys(_TEXTUAL, _test_text),
    "money": _test_money,
    "date": _test_date,
    "partialdate": _test_partial_date,
    "choice": _test_choice,
    "boolean": _test_boolean,
    "multichoice": _test_multichoice,
    "checklist": _test_checklist,
}


def _test_value(kind: str, op: str, j: _Expr, operand: Any) -> _Bool:  # noqa: ANN401
    """Whether the JSON value `j` satisfies `op`; may be NULL."""
    if op == "empty":
        return _is_empty(j)
    if op == "not_empty":
        return not_(_is_empty(j))
    return _TESTS[kind](op, j, operand)


def _containment(kind: str, op: str, key: str, operand: Any) -> _Bool | None:  # noqa: ANN401
    """The `attributes @> ...` form of a test, which the GIN index serves.

    Containment on the non-null `attributes` column is never NULL, so it needs
    no COALESCE (which would hide it from the index).
    """
    if op == "=" and kind in {"choice", "boolean"}:
        return NodeModel.attributes.contains({key: operand})
    if op == "has" and kind == "multichoice":
        return NodeModel.attributes.contains({key: list(operand)})
    return None


def _column_test(
    condition: FieldCondition,
    kind: str,
    op: str,
    operand: Any,  # noqa: ANN401
) -> _Bool:
    """A table column: some row matches; `empty` is "no row is filled"."""
    rows = _rows(NodeModel.attributes[condition.key], "row")
    cell = rows.c.value[condition.sub_key]
    if op in {"empty", "not_empty"}:
        filled = _any_row(rows, not_(_is_empty(cell)))
        return filled if op == "not_empty" else not_(filled)
    return _any_row(rows, _test_value(kind, op, cell, operand))


def _field_test(condition: FieldCondition, kind: str, ctx: ResolvedQuery) -> _Bool:
    """The condition's test with a complement read as its positive; never NULL."""
    op = COMPLEMENT_OPERATORS.get(condition.op, condition.op)
    operand = None if condition.value is None else _operand(condition.value, kind, ctx)
    if condition.sub_key is not None:
        return _column_test(condition, kind, op, operand)
    indexed = _containment(kind, op, condition.key, operand)
    if indexed is not None:
        return indexed
    j = NodeModel.attributes[condition.key]
    return _never_null(_test_value(kind, op, j, operand))


def _declares(key: str, kind: str) -> _Bool:
    """The item's own overlay declares `key` with `kind` and keeps it live.

    `IS NOT NULL AND ...` is never NULL; both containments are served by the
    `extra_schema` GIN index.
    """
    overlay = NodeModel.extra_schema
    declared = overlay.contains({"properties": {key: {"x-menagerist": {"kind": kind}}}})
    archived = overlay.contains(
        {"properties": {key: {"x-menagerist": {"archived": True}}}}
    )
    return and_(overlay.isnot(None), declared, not_(archived))


def _field(condition: FieldCondition, ctx: ResolvedQuery) -> _Bool:
    """Only items in scope can match, complements included; stale is false.

    In scope: the named type, or an item whose own overlay declares the field.
    """
    if condition in ctx.stale:
        return false()
    if condition.field_kind is not None:
        kind: str | None = condition.field_kind
        in_scope = _declares(condition.key, condition.field_kind)
    else:
        kind = ctx.field_kinds.get(
            (condition.type or "", condition.key, condition.sub_key)
        )
        in_scope = _never_null(NodeModel.type == condition.type)
    if kind is None:
        return false()
    test = _field_test(condition, kind, ctx)
    complement = condition.op in COMPLEMENT_OPERATORS
    return and_(in_scope, not_(test) if complement else test)


def _date(condition: DateCondition, ctx: ResolvedQuery) -> _Bool:
    stamp = NodeModel.created_at if condition.on == "created" else NodeModel.updated_at
    day = func.to_char(func.timezone("UTC", stamp), "YYYY-MM-DD").collate(_C)
    return _never_null(
        _ordered(condition.op, day, _operand(condition.value, "date", ctx))
    )


def _tag(condition: TagCondition) -> _Bool:
    # Containment on the non-null `tags` column: never NULL, and indexable.
    tags = NodeModel.tags
    if condition.mode == "all":
        return tags.contains(list(condition.tags))
    any_of = or_(*(tags.contains([tag]) for tag in condition.tags))
    return any_of if condition.mode == "any" else not_(any_of)


def _description(condition: DescriptionCondition) -> _Bool:
    """Never NULL; `~` is a bare ILIKE so the description trigram index serves it."""
    description = NodeModel.description
    if condition.op == "~":
        return and_(
            description.is_not(None),
            unaccent_ilike(description, like_pattern(condition.value or "")),
        )
    blank = func.coalesce(description.op("~")(_BLANK_PATTERN), true())
    return blank if condition.op == "empty" else not_(blank)


def _name(condition: NameCondition) -> _Bool:
    if condition.op == "~":
        return unaccent_ilike(NodeModel.name, like_pattern(condition.value))
    return _folded(NodeModel.name) == _folded(literal(condition.value))


def _media(condition: MediaCondition, env: QueryEnv) -> _Bool:
    """Never NULL; with no external source nothing has media to match."""
    if env.external is None:
        return false()
    predicate: _Bool = env.external.media_predicate(
        condition.mode, condition.type, env.scope
    )
    return predicate


def _collection(
    condition: CollectionCondition, ctx: ResolvedQuery, env: QueryEnv
) -> _Bool:
    """On any live target (a smart one inlined); all-stale matches nothing.

    `EXISTS` and the inlined leaves are never NULL, so `none` is a plain NOT.
    """
    live = [t for t in condition.targets if not isinstance(t, StaleTarget)]
    if not live:
        return false()
    parts: list[_Bool] = []
    manual = [t.id for t in live if isinstance(t, ManualTarget)]
    if manual and env.external is not None:
        parts.append(env.external.collection_predicate(manual, env.scope))
    parts.extend(
        true() if t.where is None else _group(t.where, ctx, env)
        for t in live
        if isinstance(t, SmartTarget)
    )
    any_of = or_(false(), *parts)
    return any_of if condition.mode == "any" else not_(any_of)


def _linked(
    condition: ConnectionCondition,
    side: Literal["out", "in"],
    ctx: ResolvedQuery,
    env: QueryEnv,
) -> _Bool:
    """A live connection at one end of the item to a live far item in scope.

    `out` means the item is the edge's source. Correlated on `edges.source_id`
    or `target_id` (both indexed); the far item is joined by primary key and
    its filter is the main tree rebound to the far row.
    """
    near, far_id = (
        (EdgeModel.source_id, EdgeModel.target_id)
        if side == "out"
        else (EdgeModel.target_id, EdgeModel.source_id)
    )
    scope = env.scope
    tests: list[_Bool] = [
        near == NodeModel.id,
        EdgeModel.deleted_at.is_(None),
        owned_by(EdgeModel, scope.user_id),
    ]
    if condition.relationship is not None:
        tests.append(EdgeModel.type == condition.relationship)
    if condition.mode == "to":
        tests.append(far_id == condition.item)
        return exists(select(literal(1)).select_from(EdgeModel).where(*tests))
    far = NodeModel.__table__.alias()
    tests += [
        far.c.deleted_at.is_(None),
        true() if scope.user_id is None else far.c.owner_id == scope.user_id,
    ]
    if condition.where is not None:
        tests.append(ClauseAdapter(far).traverse(_group(condition.where, ctx, env)))
    return exists(
        select(literal(1))
        .select_from(EdgeModel)
        .join(far, far.c.id == far_id)
        .where(*tests)
    )


def _connection(
    condition: ConnectionCondition, ctx: ResolvedQuery, env: QueryEnv
) -> _Bool:
    """Exists, none or to; never NULL. A stale relationship or item is false.

    `none` is the conjunction of one NOT EXISTS per end, which the planner turns
    into anti-joins over the edge indexes.
    """
    slug = condition.relationship
    info = None if slug is None else ctx.relationships.get(slug)
    if slug is not None and info is None:
        return false()
    if condition.mode == "to" and condition.item not in ctx.visible_items:
        return false()
    either = condition.direction == "any" or (info is not None and not info.directional)
    sides: tuple[Literal["out", "in"], ...] = ("out", "in")
    if not either:
        sides = ("out",) if condition.direction == "out" else ("in",)
    found = [_linked(condition, side, ctx, env) for side in sides]
    if condition.mode == "none":
        return and_(*(not_(each) for each in found))
    return or_(*found)


def _item_condition(condition: Condition, ctx: ResolvedQuery, env: QueryEnv) -> _Bool:
    """Type, favourite, and the conditions that need other modules' data."""
    if isinstance(condition, TypeCondition):
        return _never_null(NodeModel.type.in_(condition.slugs))
    if isinstance(condition, FavouriteCondition):
        return _never_null(NodeModel.favourite == condition.value)
    if isinstance(condition, MediaCondition):
        return _media(condition, env)
    if isinstance(condition, CollectionCondition):
        return _collection(condition, ctx, env)
    if isinstance(condition, ConnectionCondition):
        return _connection(condition, ctx, env)
    raise AssertionError(condition)


_ITEM_CONDITIONS = (
    TypeCondition,
    FavouriteCondition,
    MediaCondition,
    CollectionCondition,
    ConnectionCondition,
)


def _condition(condition: Condition, ctx: ResolvedQuery, env: QueryEnv) -> _Bool:
    """One leaf; never NULL."""
    if isinstance(condition, TextCondition):
        return search_clause(condition.q, ctx.search_exclusions)
    if isinstance(condition, DescriptionCondition):
        return _description(condition)
    if isinstance(condition, NameCondition):
        return _name(condition)
    if isinstance(condition, _ITEM_CONDITIONS):
        return _item_condition(condition, ctx, env)
    if isinstance(condition, TagCondition):
        return _tag(condition)
    if isinstance(condition, DateCondition):
        return _date(condition, ctx)
    return _field(condition, ctx)


def _group(group: Group, ctx: ResolvedQuery, env: QueryEnv) -> _Bool:
    parts = [
        _group(child, ctx, env)
        if isinstance(child, Group)
        else _condition(child, ctx, env)
        for child in group.children
    ]
    if group.op == "and":
        return and_(*parts)
    if group.op == "or":
        return or_(*parts)
    return not_(parts[0])


def compile_where(ctx: ResolvedQuery, env: QueryEnv) -> _Bool | None:
    """The filter as one boolean expression, or None for "everything"."""
    where = ctx.query.where
    return None if where is None else _group(where, ctx, env)


def _field_sort_expression(key: SortKey, ctx: ResolvedQuery) -> _Expr:
    kind = ctx.field_kinds.get((key.type or "", key.key or "", None))
    if kind is None or key.key is None:
        return cast(null(), Text)
    j = NodeModel.attributes[key.key]
    if kind in _NUMERIC:
        return case((NodeModel.type == key.type, _num(j)), else_=null())
    if kind == "money":
        return case((NodeModel.type == key.type, _num(j["value"])), else_=null())
    text = _str(j) if kind in {"date", "partialdate"} else _folded(_str(j))
    return case((NodeModel.type == key.type, text), else_=null()).collate(_C)


def _epoch(stamp: SQLColumnExpression[Any]) -> _Expr:
    """Seconds since the epoch; `timezone` makes it IMMUTABLE, so indexable."""
    return cast(func.extract("epoch", func.timezone("UTC", stamp)), Float)


def _sort_expression(key: SortKey, ctx: ResolvedQuery) -> _Expr:
    if key.by == "name":
        return _folded(NodeModel.name).collate(_C)
    if key.by == "created":
        return _epoch(NodeModel.created_at)
    if key.by == "updated":
        return _epoch(NodeModel.updated_at)
    return _field_sort_expression(key, ctx)


def sort_expressions(ctx: ResolvedQuery) -> list[_Expr]:
    """One expression per sort key, in order; each yields the hit's sort value."""
    return [_sort_expression(key, ctx) for key in ctx.query.sort]


def order_by(ctx: ResolvedQuery, exprs: list[_Expr]) -> list[_Expr]:
    """ORDER BY terms: each key, then id.

    Field keys sort nulls last. Name and the timestamps cannot be NULL, so they
    omit it, which lets an index on them (or a backward scan) serve the order.
    """
    terms = []
    for expr, key in zip(exprs, ctx.query.sort, strict=True):
        term = expr.desc() if key.dir == "desc" else expr.asc()
        terms.append(term if key.by != "field" else term.nulls_last())
    return [*terms, NodeModel.id.asc()]


def after_clause(ctx: ResolvedQuery, exprs: list[_Expr], cursor: Cursor) -> _Bool:
    """Rows strictly after `cursor` in the order `order_by` produces.

    Works when the cursor row itself is gone: only its values are used.
    """
    branches: list[_Bool] = []
    equal: list[_Bool] = []
    for expr, key, value in zip(exprs, ctx.query.sort, cursor.sort_values, strict=True):
        if value is None:
            # Nulls sort last, so nothing non-null comes after a null.
            later: _Bool = false()
            same: _Bool = expr.is_(None)
        else:
            beyond = expr < value if key.dir == "desc" else expr > value
            later = or_(beyond, expr.is_(None))
            same = expr == value
        branches.append(and_(*equal, later))
        equal.append(same)
    branches.append(and_(*equal, NodeModel.id > cursor.id))
    after = or_(*branches)
    if not ctx.query.sort:
        return after
    first, value = ctx.query.sort[0], cursor.sort_values[0]
    if first.by == "field" or value is None:
        return after
    # Implied by `after`; as a plain range it lets an index start at the cursor.
    bound = exprs[0] <= value if first.dir == "desc" else exprs[0] >= value
    return and_(bound, after)
