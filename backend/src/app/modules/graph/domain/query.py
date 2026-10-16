"""The condition tree behind advanced search: structure, limits and parsing.

A query is plain JSON on the wire and in storage. `parse_query` turns it into
frozen dataclasses, rejecting anything malformed with the path of the problem.
Checking fields against item types happens in the application layer.
"""

import re
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final, Literal, cast

from app.modules.graph.domain.node import Node
from app.shared_kernel.errors import ValidationError

QUERY_VERSION: Final = 1
MAX_DEPTH: Final = 4
MAX_CONDITIONS: Final = 50
MAX_TEXT_LENGTH: Final = 200
MAX_LIST_LENGTH: Final = 50
MAX_SORT_KEYS: Final = 3

_OPERATORS: Final = frozenset(
    {
        "=",
        "!=",
        "~",
        ">",
        ">=",
        "<",
        "<=",
        "between",
        "in",
        "not_in",
        "empty",
        "not_empty",
        "has",
        "incomplete",
        "complete",
    }
)
_NO_VALUE: Final = frozenset({"empty", "not_empty", "incomplete", "complete"})
# Each matches items of the named type for which its positive form does not.
COMPLEMENT_OPERATORS: Final[Mapping[str, str]] = {"!=": "=", "not_in": "in"}
_DATE_OPERATORS: Final = frozenset({"=", ">", ">=", "<", "<=", "between"})
_GROUP_OPS: Final = ("and", "or", "not")
_SORT_BYS: Final = frozenset({"name", "created", "updated", "field"})
_BETWEEN_LENGTH: Final = 2
_REL: Final = re.compile(r"([+-]?[0-9]{1,3})([dwmy])")
_INF: Final = float("inf")


class InvalidQueryError(ValidationError):
    """Raised when a query is malformed or does not fit the item types."""

    def __init__(self, message: str, *, path: str = "") -> None:
        super().__init__(f"{path}: {message}" if path else message)
        self.path = path


def _add_months(day: date, months: int) -> date:
    index = day.year * 12 + (day.month - 1) + months
    year, month = divmod(index, 12)
    month += 1
    last = (date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)).day
    return date(year, month, min(day.day, last))


@dataclass(frozen=True, kw_only=True)
class RelativeDate:
    """A date as an offset from today, evaluated at read time."""

    amount: int
    unit: Literal["d", "w", "m", "y"]

    def resolve(self, today: date) -> date:
        """Return the date `amount` units from `today`, clamping month ends."""
        if self.unit == "d":
            return today + timedelta(days=self.amount)
        if self.unit == "w":
            return today + timedelta(weeks=self.amount)
        months = self.amount * (12 if self.unit == "y" else 1)
        return _add_months(today, months)


@dataclass(frozen=True, kw_only=True)
class FieldReference:
    """Another top-level field on the same item, as the value to compare with."""

    key: str


@dataclass(frozen=True, kw_only=True)
class Money:
    """An amount in one currency."""

    value: float
    currency: str


type Scalar = str | int | float | bool
type Operand = Scalar | Money | RelativeDate | FieldReference | tuple[Operand, ...]


@dataclass(frozen=True, kw_only=True)
class TextCondition:
    """Free text across name, description and searchable values."""

    q: str


@dataclass(frozen=True, kw_only=True)
class TypeCondition:
    """The item is one of these types."""

    slugs: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class FavouriteCondition:
    """The item is, or is not, a favourite."""

    value: bool


@dataclass(frozen=True, kw_only=True)
class TagCondition:
    """The item carries any, all or none of these tags."""

    mode: Literal["any", "all", "none"]
    tags: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class DateCondition:
    """Compare the day an item was created or last updated."""

    on: Literal["created", "updated"]
    op: str
    value: Operand


@dataclass(frozen=True, kw_only=True)
class FieldCondition:
    """Compare a field of one item type, or a per-item field by its kind.

    `type` addresses a field of an item type; `field_kind` addresses a field an
    item declares in its own overlay. Exactly one is set. `sub_key` addresses a
    table column and is only valid with `type`.
    """

    key: str
    op: str
    type: str | None = None
    field_kind: str | None = None
    value: Operand | None = None
    sub_key: str | None = None


type Condition = (
    TextCondition
    | TypeCondition
    | FavouriteCondition
    | TagCondition
    | DateCondition
    | FieldCondition
)


@dataclass(frozen=True, kw_only=True)
class Group:
    """`and` / `or` over its children, or `not` over exactly one."""

    op: Literal["and", "or", "not"]
    children: tuple[Group | Condition, ...]


@dataclass(frozen=True, kw_only=True)
class SortKey:
    """One ordering key; nulls always sort last."""

    by: Literal["name", "created", "updated", "field"]
    dir: Literal["asc", "desc"] = "asc"
    type: str | None = None
    key: str | None = None


@dataclass(frozen=True, kw_only=True)
class Query:
    """A filter tree and an ordering. An empty ordering means creation order."""

    where: Group | None
    sort: tuple[SortKey, ...] = ()


type FieldKey = tuple[str, str, str | None]


@dataclass(frozen=True)
class QueryWarning:
    """A part of a query that no longer applies."""

    path: str
    message: str


@dataclass(frozen=True)
class FieldResolution:
    """Kinds of the fields that still exist, and what went stale."""

    kinds: dict[FieldKey, str]
    warnings: list[QueryWarning]
    stale: frozenset[FieldCondition] = frozenset()


type SortValue = str | float | None


@dataclass(frozen=True, kw_only=True)
class Cursor:
    """Where a page ended: the last row's sort values and id."""

    sort_values: tuple[SortValue, ...]
    id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class SearchHit:
    """A matching node with the sort values the repository ordered it by."""

    node: Node
    sort_values: tuple[SortValue, ...]


@dataclass(frozen=True, kw_only=True)
class ResolvedQuery:
    """A query plus everything adapters need to evaluate it.

    `field_kinds` holds only fields that still exist. A field condition whose
    key is absent, or that is in `stale` (its field or a field it references
    is gone), matches nothing.
    """

    query: Query
    field_kinds: Mapping[FieldKey, str]
    search_exclusions: Mapping[str, Sequence[str]]
    today: date
    stale: frozenset[FieldCondition] = frozenset()


def walk_conditions(
    group: Group | None, path: str = "where"
) -> Iterator[tuple[str, Condition]]:
    """Yield every condition with its JSON path, depth first, in order."""
    if group is None:
        return
    for index, child in enumerate(group.children):
        child_path = f"{path}.children[{index}]"
        if isinstance(child, Group):
            yield from walk_conditions(child, child_path)
        else:
            yield child_path, child


def _encodable(raw: str) -> bool:
    """Whether `raw` is valid UTF-8 text (no lone surrogates)."""
    try:
        raw.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _finite(value: float) -> bool:
    """Whether `value` fits a float8: not NaN, infinite or out of range."""
    try:
        number = float(value)
    except OverflowError:
        return False
    return -_INF < number < _INF


def _string(raw: object, path: str, *, name: str) -> str:
    if (
        not isinstance(raw, str)
        or not 1 <= len(raw) <= MAX_TEXT_LENGTH
        or not _encodable(raw)
    ):
        msg = f"'{name}' must be text of 1 to {MAX_TEXT_LENGTH} characters."
        raise InvalidQueryError(msg, path=path)
    return raw


def _string_list(raw: object, path: str, *, name: str) -> tuple[str, ...]:
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_LIST_LENGTH:
        msg = f"'{name}' must be a list of 1 to {MAX_LIST_LENGTH} texts."
        raise InvalidQueryError(msg, path=path)
    return tuple(_string(item, path, name=name) for item in raw)


def _relative(raw: object, path: str) -> RelativeDate:
    match = _REL.fullmatch(raw) if isinstance(raw, str) else None
    if match is None:
        msg = "Use a relative date like -30d."
        raise InvalidQueryError(msg, path=path)
    return RelativeDate(
        amount=int(match.group(1)),
        unit=cast("Literal['d', 'w', 'm', 'y']", match.group(2)),
    )


def _mapping_operand(raw: Mapping[object, object], path: str) -> Operand:
    keys = set(raw)
    if keys == {"rel"}:
        return _relative(raw["rel"], path)
    if keys == {"ref"}:
        return FieldReference(key=_string(raw["ref"], path, name="ref"))
    value = raw.get("value")
    if (
        keys == {"value", "currency"}
        and isinstance(value, int | float)
        and not isinstance(value, bool)
        and _finite(value)
    ):
        return Money(
            value=float(value),
            currency=_string(raw["currency"], path, name="currency"),
        )
    msg = "That is not a valid value."
    raise InvalidQueryError(msg, path=path)


def _operand(raw: object, path: str) -> Operand:
    if isinstance(raw, bool) or (isinstance(raw, int | float) and _finite(raw)):
        return raw
    if isinstance(raw, str):
        if len(raw) > MAX_TEXT_LENGTH:
            msg = "That value is too long."
            raise InvalidQueryError(msg, path=path)
        if not _encodable(raw):
            msg = "That is not a valid value."
            raise InvalidQueryError(msg, path=path)
        return raw
    if isinstance(raw, Mapping):
        return _mapping_operand(raw, path)
    msg = "That is not a valid value."
    raise InvalidQueryError(msg, path=path)


def _operand_list(raw: object, path: str, *, op: str) -> tuple[Operand, ...]:
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_LIST_LENGTH:
        msg = f"'{op}' needs 1 to {MAX_LIST_LENGTH} values."
        raise InvalidQueryError(msg, path=path)
    return tuple(_operand(item, path) for item in raw)


def _value(op: str, data: Mapping[str, object], path: str) -> Operand | None:
    if op in _NO_VALUE:
        if "value" in data:
            msg = f"'{op}' takes no value."
            raise InvalidQueryError(msg, path=path)
        return None
    if "value" not in data:
        msg = f"'{op}' needs a value."
        raise InvalidQueryError(msg, path=path)
    raw = data["value"]
    if op == "between":
        if not isinstance(raw, list) or len(raw) != _BETWEEN_LENGTH:
            msg = "'between' needs [low, high]."
            raise InvalidQueryError(msg, path=path)
        return tuple(_operand(item, path) for item in raw)
    if op == "has" and not isinstance(raw, list):
        return (_operand(raw, path),)
    if op in {"in", "not_in", "has"}:
        return _operand_list(raw, path, op=op)
    return _operand(raw, path)


def _text(data: Mapping[str, object], path: str) -> TextCondition:
    return TextCondition(q=_string(data.get("q"), path, name="q"))


def _type(data: Mapping[str, object], path: str) -> TypeCondition:
    return TypeCondition(slugs=_string_list(data.get("in"), path, name="in"))


def _favourite(data: Mapping[str, object], path: str) -> FavouriteCondition:
    value = data.get("value")
    if not isinstance(value, bool):
        msg = "'value' must be true or false."
        raise InvalidQueryError(msg, path=path)
    return FavouriteCondition(value=value)


def _tag(data: Mapping[str, object], path: str) -> TagCondition:
    mode = data.get("mode")
    if not isinstance(mode, str) or mode not in {"any", "all", "none"}:
        msg = "'mode' must be any, all or none."
        raise InvalidQueryError(msg, path=path)
    return TagCondition(
        mode=cast("Literal['any', 'all', 'none']", mode),
        tags=_string_list(data.get("tags"), path, name="tags"),
    )


def _date(data: Mapping[str, object], path: str) -> DateCondition:
    on = data.get("on")
    op = data.get("op")
    if (
        not isinstance(on, str)
        or on not in {"created", "updated"}
        or not isinstance(op, str)
        or op not in _DATE_OPERATORS
    ):
        msg = "Use on: created or updated with a comparison."
        raise InvalidQueryError(msg, path=path)
    value = _value(op, data, path)
    return DateCondition(
        on=cast("Literal['created', 'updated']", on),
        op=op,
        value=cast("Operand", value),
    )


def _has_reference(value: Operand | None) -> bool:
    items = value if isinstance(value, tuple) else (value,)
    return any(isinstance(item, FieldReference) for item in items)


def _field(data: Mapping[str, object], path: str) -> FieldCondition:
    op = data.get("op")
    if not isinstance(op, str) or op not in _OPERATORS:
        msg = "Unknown operator."
        raise InvalidQueryError(msg, path=path)
    raw_type = data.get("type")
    raw_kind = data.get("field_kind")
    if raw_type is not None and raw_kind is not None:
        msg = "Name an item type or a field kind, not both."
        raise InvalidQueryError(msg, path=path)
    if raw_kind is None:
        field_type: str | None = _string(raw_type, path, name="type")
        field_kind = None
    else:
        field_type = None
        field_kind = _string(raw_kind, path, name="field_kind")
    sub_key = data.get("sub_key")
    value = _value(op, data, path)
    if field_kind is not None and (sub_key is not None or _has_reference(value)):
        msg = "A per-item field has no column and cannot be compared with a field."
        raise InvalidQueryError(msg, path=path)
    return FieldCondition(
        type=field_type,
        field_kind=field_kind,
        key=_string(data.get("key"), path, name="key"),
        sub_key=None if sub_key is None else _string(sub_key, path, name="sub_key"),
        op=op,
        value=value,
    )


_CONDITION_PARSERS: Final[
    Mapping[str, Callable[[Mapping[str, object], str], Condition]]
] = {
    "text": _text,
    "type": _type,
    "favourite": _favourite,
    "tag": _tag,
    "date": _date,
    "field": _field,
}


def _sort_key(item: object, path: str) -> SortKey:
    by = item.get("by") if isinstance(item, Mapping) else None
    if not isinstance(item, Mapping) or not isinstance(by, str) or by not in _SORT_BYS:
        msg = "Sort by name, created, updated or field."
        raise InvalidQueryError(msg, path=path)
    direction = item.get("dir", "asc")
    if not isinstance(direction, str) or direction not in {"asc", "desc"}:
        msg = "'dir' must be asc or desc."
        raise InvalidQueryError(msg, path=path)
    by = cast("Literal['name', 'created', 'updated', 'field']", item["by"])
    direction = cast("Literal['asc', 'desc']", direction)
    if by != "field":
        return SortKey(by=by, dir=direction)
    return SortKey(
        by=by,
        dir=direction,
        type=_string(item.get("type"), path, name="type"),
        key=_string(item.get("key"), path, name="key"),
    )


def _sort(raw: object) -> tuple[SortKey, ...]:
    if not isinstance(raw, list) or len(raw) > MAX_SORT_KEYS:
        msg = f"Sort by up to {MAX_SORT_KEYS} keys."
        raise InvalidQueryError(msg, path="sort")
    return tuple(_sort_key(item, f"sort[{index}]") for index, item in enumerate(raw))


class _Parser:
    def __init__(self) -> None:
        self._conditions = 0

    def group(self, data: object, path: str, depth: int) -> Group:
        if depth > MAX_DEPTH:
            msg = f"Groups can be nested up to {MAX_DEPTH} deep."
            raise InvalidQueryError(msg, path=path)
        if not isinstance(data, Mapping) or data.get("op") not in _GROUP_OPS:
            msg = "Expected a group (and, or, not)."
            raise InvalidQueryError(msg, path=path)
        children = data.get("children")
        if not isinstance(children, list) or not children:
            msg = "A group needs at least one child."
            raise InvalidQueryError(msg, path=path)
        if data["op"] == "not" and len(children) != 1:
            msg = "'not' takes exactly one child."
            raise InvalidQueryError(msg, path=path)
        return Group(
            op=cast("Literal['and', 'or', 'not']", data["op"]),
            children=tuple(
                self.child(child, f"{path}.children[{index}]", depth)
                for index, child in enumerate(children)
            ),
        )

    def child(self, data: object, path: str, depth: int) -> Group | Condition:
        if isinstance(data, Mapping) and "kind" not in data:
            return self.group(data, path, depth + 1)
        return self.condition(data, path)

    def condition(self, data: object, path: str) -> Condition:
        self._conditions += 1
        if self._conditions > MAX_CONDITIONS:
            msg = f"A query can have up to {MAX_CONDITIONS} conditions."
            raise InvalidQueryError(msg, path=path)
        if not isinstance(data, Mapping):
            msg = "Expected a condition."
            raise InvalidQueryError(msg, path=path)
        kind = data.get("kind")
        parser = _CONDITION_PARSERS.get(kind) if isinstance(kind, str) else None
        if parser is None:
            msg = "Unknown condition kind."
            raise InvalidQueryError(msg, path=path)
        return parser(data, path)


def parse_query(data: object) -> Query:
    """Parse a query from its JSON form.

    Raises:
        InvalidQueryError: If the shape, a limit or a value is wrong; the error
            carries the JSON path of the first problem.
    """
    if not isinstance(data, Mapping):
        msg = "The query must be an object."
        raise InvalidQueryError(msg)
    version = data.get("v")
    if isinstance(version, bool) or version != QUERY_VERSION:
        msg = f"Unsupported query version; expected {QUERY_VERSION}."
        raise InvalidQueryError(msg, path="v")
    parser = _Parser()
    raw_where = data.get("where")
    where = None if raw_where is None else parser.group(raw_where, "where", 1)
    return Query(where=where, sort=_sort(data.get("sort", [])))
