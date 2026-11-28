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
    case,
    cast,
    distinct,
    func,
    literal,
    null as sql_null,
    select,
)
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
    MeasureSource,
    MeasureValue,
    ResolvedMeasure,
    tidy,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

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


def statement(measure: ResolvedMeasure) -> Select[Any]:
    """The `SELECT` for one measure, to which the caller adds scope and filter.

    A money measure also selects its currency and groups by it, so currencies are
    never mixed.
    """
    if not measure.sources:
        return select(func.count()).select_from(NodeModel)
    value = _by_type(measure, _value(measure.kind or ""))
    if not measure.per_currency:
        return select(_function(measure, value))
    currency = _by_type(measure, _currency)
    return (
        select(currency, _function(measure, value))
        .where(currency.is_not(None), value.is_not(None))
        .group_by(currency)
        .order_by(currency.collate(_C))
    )


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
