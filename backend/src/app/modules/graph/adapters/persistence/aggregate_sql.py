"""Evaluate aggregate measures in SQL.

The twin of `aggregate_eval`: the same items give the same answers, to the same
number of decimal places. A measure becomes one `SELECT` over the items the query
matches; the caller adds the scope and the query's own `WHERE`. A value is read
from the item's details the way a search reads a field, and an item whose field is
empty or of another shape is left out of that measure.
"""

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    Numeric,
    Select,
    and_,
    case,
    cast,
    distinct,
    false,
    func,
    literal,
    literal_column,
    null as sql_null,
    or_,
    select,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql.elements import ColumnElement

from app.modules.graph.adapters.persistence.models import NodeModel
from app.modules.graph.adapters.persistence.query_sql import (
    _C,
    _FLOAT_MAX,
    _NUMERIC,
    _str,
    _typed,
)
from app.modules.graph.domain.aggregate import (
    MONEY,
    CurrencyValue,
    GroupValue,
    Measure,
    MeasureSource,
    MeasureValue,
    ResolvedGroup,
    ResolvedMeasure,
    tidy,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Sequence

type _Expr = ColumnElement[Any]


def _numeric(j: _Expr) -> _Expr:
    """A JSON number as an exact numeric, or NULL when it is not one a float holds."""
    in_range = func.abs(cast(j, Numeric)) <= literal(_FLOAT_MAX, Numeric)
    # Nested CASEs: the numeric cast must only see JSON numbers.
    return _typed(j, "number", case((in_range, cast(j, Numeric)), else_=sql_null()))


def _currency(source: MeasureSource) -> _Expr:
    return _str(NodeModel.attributes[source.key]["currency"])


def _value(kind: str) -> Callable[[MeasureSource], _Expr]:
    """What one source reads, for a field of this kind."""

    def read(source: MeasureSource) -> _Expr:
        j = NodeModel.attributes[source.key]
        if kind in _NUMERIC:
            return _numeric(j)
        if kind == MONEY:
            # An amount with no currency is no amount, as in memory.
            return case(
                (_currency(source).is_not(None), _numeric(j["value"])),
                else_=sql_null(),
            )
        if kind == "boolean":
            return _typed(j, "boolean", cast(j, Boolean))
        return _str(j)

    return read


def _by_type(measure: ResolvedMeasure, read: Callable[[MeasureSource], _Expr]) -> _Expr:
    """The expression that reads each item through the source for its type."""
    return case(
        *(
            (NodeModel.type.in_(source.types), read(source))
            for source in measure.sources
        ),
        else_=sql_null(),
    )


def _function(measure: ResolvedMeasure, expr: _Expr) -> _Expr:
    fn = measure.measure.fn
    if fn == "count":
        return func.count(expr)
    if fn == "distinct":
        return func.count(distinct(expr))
    if fn == "sum":
        return func.sum(expr)
    if fn == "avg":
        return func.avg(expr)
    ordered = expr if measure.kind in _NUMERIC | {MONEY} else expr.collate(_C)
    return func.min(ordered) if fn == "min" else func.max(ordered)


# What a grouped count of items is measured with.
ITEMS = ResolvedMeasure(measure=Measure(fn="count"), kind=None, sources=())

# The keys of an item that belongs to no group: one NULL.
_UNSET = literal_column("'[null]'::jsonb", JSONB)


def _group_keys(group: ResolvedGroup) -> _Expr:
    """A JSON array of the keys of the groups an item is in, `[null]` for none."""
    if group.group.by == "type":
        return func.jsonb_build_array(NodeModel.type, type_=JSONB)
    if group.group.by == "tag":
        return case(
            (func.jsonb_array_length(NodeModel.tags) == 0, _UNSET), else_=NodeModel.tags
        )
    reads = []
    for source in group.sources:
        j = NodeModel.attributes[source.key]
        json_type = func.jsonb_typeof(j)
        if group.kind == "multichoice":
            held = and_(json_type == "array", func.jsonb_array_length(j) > 0)
            reads.append(
                (NodeModel.type.in_(source.types), case((held, j), else_=_UNSET))
            )
            continue
        named = "boolean" if group.kind == "boolean" else "string"
        reads.append(
            (
                NodeModel.type.in_(source.types),
                case(
                    (json_type == named, func.jsonb_build_array(j, type_=JSONB)),
                    else_=_UNSET,
                ),
            )
        )
    return case(*reads, else_=_UNSET)


def _group_rows(group: ResolvedGroup) -> Any:  # noqa: ANN401
    """A lateral join: one row per distinct key of each item, with the key as `gkey`."""
    key = func.jsonb_array_elements_text(_group_keys(group)).column_valued("gkey")
    return select(key).distinct().lateral("g")


def statement(
    measure: ResolvedMeasure, group: ResolvedGroup | None = None
) -> Select[Any]:
    """The `SELECT` for one measure, to which the caller adds scope and filter.

    A money measure also selects its currency and groups by it, so currencies are
    never mixed. With a `group`, each row leads with the key of a group and an item
    is counted in every group it is in.
    """
    lead: list[_Expr] = []
    rows = None
    if group is not None:
        rows = _group_rows(group)
        lead = [rows.c.gkey]

    def build(*columns: _Expr) -> Select[Any]:
        stmt = select(*lead, *columns).select_from(NodeModel)
        if rows is None:
            return stmt
        return stmt.join(rows, true()).group_by(*lead)

    if not measure.sources:
        return build(func.count())
    value = _by_type(measure, _value(measure.kind or ""))
    if not measure.per_currency:
        return build(_function(measure, value))
    currency = _by_type(measure, _currency)
    return (
        build(currency, _function(measure, value))
        .where(currency.is_not(None), value.is_not(None))
        .group_by(currency)
        .order_by(currency.collate(_C))
    )


def outside(group: ResolvedGroup, shown: Collection[str | None]) -> Select[Any]:
    """The ids of the items in a group that is not among the `shown` keys."""
    rows = _group_rows(group)
    named = [key for key in shown if key is not None]
    hidden = or_(
        and_(rows.c.gkey.is_(None), true() if None not in shown else false()),
        and_(rows.c.gkey.is_not(None), rows.c.gkey.not_in(named)),
    )
    return select(NodeModel.id).select_from(NodeModel).join(rows, true()).where(hidden)


def _answer(measure: ResolvedMeasure, raw: object) -> float | int | str | None:
    if raw is None:
        return None
    if isinstance(raw, Decimal):
        if measure.measure.fn in {"sum", "avg"}:
            return tidy(raw)
        return float(raw)
    return raw if isinstance(raw, int | str) else None


def read(measure: ResolvedMeasure, rows: Sequence[Any]) -> MeasureValue:
    """The measure's value from the rows its statement returned."""
    if measure.per_currency:
        return MeasureValue(
            currencies=tuple(
                CurrencyValue(
                    currency=str(row[0]), value=float(_answer(measure, row[1]) or 0)
                )
                for row in rows
            )
        )
    return MeasureValue(value=_answer(measure, rows[0][0]))


def read_groups(
    measure: ResolvedMeasure, rows: Sequence[Any]
) -> dict[str | None, MeasureValue]:
    """The measure's value in each group from the rows its grouped statement gave."""
    if not measure.per_currency:
        return {row[0]: MeasureValue(value=_answer(measure, row[1])) for row in rows}
    found: dict[str | None, list[CurrencyValue]] = {}
    for key, currency, raw in rows:
        found.setdefault(key, []).append(
            CurrencyValue(
                currency=str(currency), value=float(_answer(measure, raw) or 0)
            )
        )
    return {key: MeasureValue(currencies=tuple(v)) for key, v in found.items()}


def group_values(
    counts: Sequence[Any], answers: Sequence[dict[str | None, MeasureValue]]
) -> list[GroupValue]:
    """Every group's size and its value for each measure, from per-group answers."""
    return [
        GroupValue(
            key=key,
            count=size,
            values=tuple(a.get(key, MeasureValue()) for a in answers),
        )
        for key, size in counts
    ]
