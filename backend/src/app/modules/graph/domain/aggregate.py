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
# Most groups an aggregate lists; the rest are counted in one `other` row.
MAX_GROUPS: Final = 100

type GroupAxis = Literal["field", "type", "tag", "related"]
type Direction = Literal["out", "in", "any"]
type GroupOrder = Literal["key", "count", "measure"]
type AggregateFn = Literal["count", "sum", "avg", "min", "max", "distinct"]

FUNCTIONS: Final[frozenset[str]] = frozenset(
    {"count", "sum", "avg", "min", "max", "distinct"}
)

# The kinds of field whose values name a group. A multiple-choice value is in one
# group for each choice it holds.
GROUPABLE_KINDS: Final = frozenset({"choice", "multichoice", "boolean", "text"})

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


def _field_ref(
    raw: Mapping[str, Any], path: str
) -> tuple[str | None, str | None, str | None]:
    """The `type`, `key` and `origin` of a field a measure or a grouping names."""
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
    return type_slug, key, origin


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
    type_slug, key, origin = _field_ref(raw, path)
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


@dataclass(frozen=True, kw_only=True)
class GroupBy:
    """What to split the matching items by: a field, the item type, a tag or an item.

    A field is named as a measure's is (`type` and `key`, or `origin`). `related`
    groups by the item at the other end of a named `relationship`, read in
    `direction` as a connection condition reads it. `order`
    sorts the groups by their key, their item count or one measure's value (the
    index in `measure`); `descending` defaults to ascending for a key and
    descending for the others.
    """

    by: GroupAxis
    type: str | None = None
    key: str | None = None
    origin: str | None = None
    relationship: str | None = None
    direction: Direction = "any"
    order: GroupOrder = "key"
    measure: int | None = None
    descending: bool | None = None
    limit: int = MAX_GROUPS

    @property
    def is_descending(self) -> bool:
        """Whether the groups run from high to low."""
        if self.descending is not None:
            return self.descending
        return self.order != "key"


@dataclass(frozen=True, kw_only=True)
class ResolvedGroup:
    """A grouping checked against the item types, ready for a repository.

    `sources` is empty unless grouping by a field. `kind` is the one kind every
    source holds. `directional` is whether a related grouping's relationship has a
    direction; one that has none is read from either end.
    """

    group: GroupBy
    kind: str | None
    sources: tuple[MeasureSource, ...]
    directional: bool = True


@dataclass(frozen=True, kw_only=True)
class GroupValue:
    """One group: its key (None for items with no value), size and measure values.

    An item in several groups (a tag, a multiple-choice value, a related item)
    counts in each. A group of related items has the item's name as `label`.
    """

    key: str | None
    count: int
    values: tuple[MeasureValue, ...]
    label: str | None = None


def _group_order(raw: Mapping[str, Any], path: str) -> tuple[GroupOrder, int | None]:
    """The `order` of a grouping and, for an order by a measure, its index."""
    order = raw.get("order", "key")
    if order not in {"key", "count", "measure"}:
        raise InvalidQueryError("`order` is one of count, key, measure.", path=path)
    measure = raw.get("measure")
    if order == "measure":
        if not isinstance(measure, int) or isinstance(measure, bool) or measure < 0:
            raise InvalidQueryError(
                "Ordering by a measure needs its index in `measure`.", path=path
            )
    elif measure is not None:
        raise InvalidQueryError("`measure` goes with `order` of measure.", path=path)
    return cast("GroupOrder", order), measure


def _relation(
    raw: Mapping[str, Any], by: object, path: str
) -> tuple[str | None, Direction]:
    """The `relationship` and `direction` of a related grouping."""
    relationship = _text(raw, "relationship", path)
    direction = raw.get("direction")
    if by != "related":
        if relationship is not None or direction is not None:
            raise InvalidQueryError(
                "`relationship` and `direction` go with `by` of related.", path=path
            )
        return None, "any"
    if relationship is None:
        raise InvalidQueryError(
            "Grouping by related items needs a `relationship`.", path=path
        )
    if direction is not None and direction not in {"out", "in", "any"}:
        raise InvalidQueryError("`direction` is out, in or any.", path=path)
    return relationship, cast("Direction", direction or "any")


def parse_group_by(raw: object) -> GroupBy:
    """Parse a request's grouping.

    Raises:
        InvalidQueryError: With the path of anything that is not a grouping.
    """
    path = "group_by"
    if not isinstance(raw, Mapping):
        raise InvalidQueryError("`group_by` is an object.", path=path)
    unknown = set(raw) - {
        "by", "type", "key", "origin", "relationship", "direction",
        "order", "measure", "descending", "limit",
    }  # fmt: skip
    if unknown:
        raise InvalidQueryError(
            f"Unknown grouping property: {sorted(unknown)[0]}.", path=path
        )
    by = raw.get("by")
    if by not in {"field", "type", "tag", "related"}:
        raise InvalidQueryError("`by` is one of field, related, tag, type.", path=path)
    type_slug, key, origin = _field_ref(raw, path)
    has_field = key is not None or origin is not None
    if by == "field" and not has_field:
        raise InvalidQueryError("Grouping by a field needs one.", path=path)
    if by != "field" and has_field:
        raise InvalidQueryError(f"Grouping by {by} takes no field to read.", path=path)
    relationship, direction = _relation(raw, by, path)
    order, measure = _group_order(raw, path)
    descending = raw.get("descending")
    if descending is not None and not isinstance(descending, bool):
        raise InvalidQueryError("`descending` is true or false.", path=path)
    limit = raw.get("limit", MAX_GROUPS)
    if (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or not 1 <= limit <= MAX_GROUPS
    ):
        raise InvalidQueryError(
            f"`limit` is a whole number from 1 to {MAX_GROUPS}.", path=path
        )
    return GroupBy(
        by=cast("GroupAxis", by),
        type=type_slug,
        key=key,
        origin=origin,
        relationship=relationship,
        direction=direction,
        order=order,
        measure=measure,
        descending=descending,
        limit=limit,
    )


def _sort_value(group: GroupValue, by: GroupBy) -> float | int | str | None:
    if by.order == "count":
        return group.count
    if by.order == "measure":
        return group.values[by.measure or 0].value
    return group.label or group.key


def arrange_groups(
    groups: Sequence[GroupValue], by: GroupBy
) -> tuple[list[GroupValue], list[GroupValue]]:
    """Sort the groups as asked and split them into those shown and the rest.

    Ties, and groups with nothing to sort by (the unset group when sorting by
    key, an empty measure), come last, in key order with the unset group at the end.
    """
    by_key = sorted(
        groups, key=lambda g: (g.key is None, g.label or g.key or "", g.key or "")
    )
    keyed = [(g, _sort_value(g, by)) for g in by_key]
    with_value = sorted(
        ((g, v) for g, v in keyed if v is not None),
        key=lambda pair: pair[1],
        reverse=by.is_descending,
    )
    ordered = [g for g, _ in with_value] + [g for g, v in keyed if v is None]
    return ordered[: by.limit], ordered[by.limit :]
