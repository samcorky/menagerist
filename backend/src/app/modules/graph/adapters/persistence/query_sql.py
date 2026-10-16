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
from typing import TYPE_CHECKING, Any, Final

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
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql.elements import ColumnElement

from app.modules.graph.adapters.persistence.models import NodeModel
from app.modules.graph.adapters.persistence.search_sql import (
    like_pattern,
    search_clause,
    unaccent_ilike,
)
from app.modules.graph.domain.query import (
    COMPLEMENT_OPERATORS,
    Condition,
    Cursor,
    DateCondition,
    FavouriteCondition,
    FieldCondition,
    FieldReference,
    Group,
    Money,
    Operand,
    RelativeDate,
    ResolvedQuery,
    SortKey,
    TagCondition,
    TextCondition,
    TypeCondition,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from sqlalchemy import SQLColumnExpression
    from sqlalchemy.sql.selectable import TableValuedAlias

type _Expr = ColumnElement[Any]
type _Bool = ColumnElement[bool]

_NUMERIC: Final = frozenset({"number", "duration", "rating"})
_TEXTUAL: Final = frozenset({"text", "url", "email", "phone", "longtext"})
_C: Final = "C"  # byte-wise collation: Python's code-point string order
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


def _field(condition: FieldCondition, ctx: ResolvedQuery) -> _Bool:
    """Only items of the named type can match, complements included; stale is false."""
    if condition in ctx.stale or condition.type is None:
        # TODO(task 2): per-item conditions (type is None) match nothing until
        # compiled against the item's own overlay.
        return false()
    kind = ctx.field_kinds.get((condition.type, condition.key, condition.sub_key))
    if kind is None:
        return false()
    of_type = _never_null(NodeModel.type == condition.type)
    test = _field_test(condition, kind, ctx)
    complement = condition.op in COMPLEMENT_OPERATORS
    return and_(of_type, not_(test) if complement else test)


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


def _condition(condition: Condition, ctx: ResolvedQuery) -> _Bool:
    """One leaf; never NULL."""
    if isinstance(condition, TextCondition):
        return search_clause(condition.q, ctx.search_exclusions)
    if isinstance(condition, TypeCondition):
        return _never_null(NodeModel.type.in_(condition.slugs))
    if isinstance(condition, FavouriteCondition):
        return _never_null(NodeModel.favourite == condition.value)
    if isinstance(condition, TagCondition):
        return _tag(condition)
    if isinstance(condition, DateCondition):
        return _date(condition, ctx)
    return _field(condition, ctx)


def _group(group: Group, ctx: ResolvedQuery) -> _Bool:
    parts = [
        _group(child, ctx) if isinstance(child, Group) else _condition(child, ctx)
        for child in group.children
    ]
    if group.op == "and":
        return and_(*parts)
    if group.op == "or":
        return or_(*parts)
    return not_(parts[0])


def compile_where(ctx: ResolvedQuery) -> _Bool | None:
    """The filter as one boolean expression, or None for "everything"."""
    where = ctx.query.where
    return None if where is None else _group(where, ctx)


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
