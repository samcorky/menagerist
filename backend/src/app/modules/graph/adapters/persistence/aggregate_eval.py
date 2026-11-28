"""Evaluate aggregate measures over items in memory.

The twin of `aggregate_sql`: the same items give the same answers, to the same
number of decimal places. Both read a value the way a search reads a field, and
leave an item out of a measure when its field is empty or of another shape.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal
from typing import TYPE_CHECKING

from app.modules.graph.adapters.persistence.query_eval import _number
from app.modules.graph.domain.aggregate import (
    MONEY,
    CurrencyValue,
    MeasureValue,
    ResolvedMeasure,
    tidy,
)

if TYPE_CHECKING:
    from app.modules.graph.domain.node import Node

_NUMERIC = frozenset({"number", "duration", "rating"})

type _Value = Decimal | str | bool


def _decimal(value: object) -> Decimal | None:
    """A JSON number as the exact decimal its text spells, or None if it is not one."""
    number = _number(value)
    if number is None:
        return None
    return Decimal(value) if isinstance(value, int) else Decimal(repr(number))


def _scalar(kind: str, raw: object) -> _Value | None:
    if kind in _NUMERIC:
        return _decimal(raw)
    if kind == "boolean":
        return raw if isinstance(raw, bool) else None
    return raw if isinstance(raw, str) else None


def _read(node: Node, measure: ResolvedMeasure) -> tuple[str | None, _Value | None]:
    """The currency (money only) and value a node gives the measure, if any."""
    kind = measure.kind or ""
    for source in measure.sources:
        if node.type not in source.types:
            continue
        raw = node.attributes.get(source.key)
        if kind != MONEY:
            return None, _scalar(kind, raw)
        if not isinstance(raw, Mapping):
            return None, None
        currency = raw.get("currency")
        amount = _decimal(raw.get("value"))
        if not isinstance(currency, str) or amount is None:
            return None, None
        return currency, amount
    return None, None


def _apply(fn: str, values: Sequence[_Value]) -> float | int | str | None:
    if fn in {"count", "distinct"}:
        return len(values) if fn == "count" else len(set(values))
    if not values:
        return None
    if fn in {"sum", "avg"}:
        total = sum((v for v in values if isinstance(v, Decimal)), Decimal(0))
        return tidy(total if fn == "sum" else total / len(values))
    pick = min if fn == "min" else max
    best = pick(values)
    return float(best) if isinstance(best, Decimal) else str(best)


def measure_values(
    nodes: Iterable[Node], measures: Sequence[ResolvedMeasure]
) -> list[MeasureValue]:
    """One value per measure over the nodes the query matched."""
    matched = list(nodes)
    answers: list[MeasureValue] = []
    for measure in measures:
        fn = measure.measure.fn
        if not measure.sources:
            answers.append(MeasureValue(value=len(matched)))
            continue
        reads = [_read(node, measure) for node in matched]
        if not measure.per_currency:
            values = [value for _, value in reads if value is not None]
            answers.append(MeasureValue(value=_apply(fn, values)))
            continue
        by_currency: dict[str, list[_Value]] = defaultdict(list)
        for currency, value in reads:
            if currency is not None and value is not None:
                by_currency[currency].append(value)
        answers.append(
            MeasureValue(
                currencies=tuple(
                    CurrencyValue(
                        currency=currency, value=float(_apply(fn, values) or 0)
                    )
                    for currency, values in sorted(by_currency.items())
                )
            )
        )
    return answers
