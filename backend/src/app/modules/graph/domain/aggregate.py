"""What an aggregate measures: a function over a field of the items a query matches.

A measure is plain JSON on the wire. `parse_measures` turns it into frozen
dataclasses, rejecting anything malformed with the path of the problem. Checking
a measure against item types happens in the application layer, which resolves
each into the concrete fields (`ResolvedMeasure`) the repositories evaluate.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal, cast

from app.modules.graph.domain.query import InvalidQueryError

MAX_MEASURES: Final = 10
# Totals and averages are given to this many decimal places, in SQL and in memory.
PLACES: Final = 6
MAX_KEY_LENGTH: Final = 200

type AggregateFn = Literal["count", "sum", "avg", "min", "max", "distinct"]

FUNCTIONS: Final[frozenset[str]] = frozenset(
    {"count", "sum", "avg", "min", "max", "distinct"}
)

# Money is added up per currency, never converted.
MONEY: Final = "money"

# Which kinds of field each function reads. `count` also counts items with no field.
_ADDABLE: Final = frozenset({"number", "duration", "rating", MONEY})
_ORDERED: Final = _ADDABLE | {"date", "partialdate"}
_DISTINCT: Final = _ORDERED | {
    "text",
    "url",
    "email",
    "phone",
    "choice",
    "boolean",
}
KINDS_BY_FUNCTION: Final[Mapping[str, frozenset[str] | None]] = {
    # None: any kind, as the count is of items that have a value.
    "count": None,
    "sum": _ADDABLE,
    "avg": _ADDABLE,
    "min": _ORDERED,
    "max": _ORDERED,
    "distinct": frozenset(_DISTINCT),
}


@dataclass(frozen=True, kw_only=True)
class Measure:
    """One function over one field.

    A field is one item type's field (`type` and `key`), or every type field
    copied from one saved field (`origin`). `count` with no field counts the items.
    """

    fn: AggregateFn
    type: str | None = None
    key: str | None = None
    origin: str | None = None

    @property
    def has_field(self) -> bool:
        """Whether the measure reads a field, not just the items."""
        return self.key is not None or self.origin is not None


@dataclass(frozen=True, kw_only=True)
class MeasureSource:
    """Where one item type (and its subtypes) holds the field a measure reads."""

    types: tuple[str, ...]
    key: str


@dataclass(frozen=True, kw_only=True)
class ResolvedMeasure:
    """A measure checked against the item types, ready for a repository.

    `sources` is empty for a count of items. `kind` is the one kind every source
    holds, or None with no field.
    """

    measure: Measure
    kind: str | None
    sources: tuple[MeasureSource, ...]

    @property
    def per_currency(self) -> bool:
        """Whether the answer is one value per currency.

        A count of items with an amount is one number, whatever the currency.
        """
        return self.kind == MONEY and self.measure.fn != "count"


@dataclass(frozen=True, kw_only=True)
class CurrencyValue:
    """An aggregate of one currency's amounts."""

    currency: str
    value: float


@dataclass(frozen=True, kw_only=True)
class MeasureValue:
    """What a measure came to.

    `value` is the answer, or None when no item had a value to read. A money
    measure has `currencies` instead, sorted by currency code.
    """

    value: float | int | str | None = None
    currencies: tuple[CurrencyValue, ...] = ()


def _text(raw: Mapping[str, Any], name: str, path: str) -> str | None:
    value = raw.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > MAX_KEY_LENGTH:
        raise InvalidQueryError(f"`{name}` must be a non-empty string.", path=path)
    return value


def parse_measure(raw: object, path: str) -> Measure:
    """Parse one measure.

    Raises:
        InvalidQueryError: With `path` for anything that is not a measure.
    """
    if not isinstance(raw, Mapping):
        raise InvalidQueryError("A measure is an object.", path=path)
    unknown = set(raw) - {"fn", "type", "key", "origin"}
    if unknown:
        msg = f"Unknown measure property: {sorted(unknown)[0]}."
        raise InvalidQueryError(msg, path=path)
    fn = raw.get("fn")
    if fn not in FUNCTIONS:
        raise InvalidQueryError(
            f"`fn` is one of {', '.join(sorted(FUNCTIONS))}.", path=path
        )
    type_slug = _text(raw, "type", path)
    key = _text(raw, "key", path)
    origin = _text(raw, "origin", path)
    if origin is not None and (type_slug is not None or key is not None):
        raise InvalidQueryError(
            "Name a saved field with `origin`, or a type's field with `type` and"
            + " `key`, not both.",
            path=path,
        )
    if origin is None and (type_slug is None) != (key is None):
        raise InvalidQueryError(
            "A type's field needs both `type` and `key`.", path=path
        )
    if fn != "count" and origin is None and key is None:
        raise InvalidQueryError(f"`{fn}` needs a field to read.", path=path)
    return Measure(fn=cast("AggregateFn", fn), type=type_slug, key=key, origin=origin)


def parse_measures(raw: Sequence[object]) -> tuple[Measure, ...]:
    """Parse a request's measures.

    Raises:
        InvalidQueryError: For none, too many, or a malformed measure.
    """
    if not 1 <= len(raw) <= MAX_MEASURES:
        raise InvalidQueryError(f"Send 1 to {MAX_MEASURES} measures.", path="measures")
    return tuple(parse_measure(item, f"measures[{n}]") for n, item in enumerate(raw))


def tidy(value: Any) -> float:  # noqa: ANN401
    """A total or an average (a `Decimal`) as the number a response carries."""
    return float(round(value, PLACES))
