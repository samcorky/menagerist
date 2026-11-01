"""Check a parsed query against item-type schemas.

A field that no longer exists is a warning and the condition matches nothing.
A wrong operator or value for a field that does exist is a 400.
"""

import re
import uuid
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any, Final

from app.modules.graph.application.field_kinds import (
    KIND_OPERATORS,
    NO_VALUE_OPERATORS,
    REF_KINDS,
    kind_of,
)
from app.modules.graph.application.schema_meta import NAMESPACE
from app.modules.graph.domain.query import (
    ConnectionCondition,
    DateCondition,
    FieldCondition,
    FieldKey,
    FieldReference,
    FieldResolution,
    Group,
    InvalidQueryError,
    Money,
    Operand,
    Query,
    QueryWarning,
    RelationshipInfo,
    RelativeDate,
    walk_conditions,
)

SORTABLE_KINDS: Final = frozenset(
    {
        "text",
        "url",
        "email",
        "phone",
        "number",
        "duration",
        "rating",
        "money",
        "date",
        "partialdate",
        "choice",
    }
)
_PARTIAL_DATE: Final = re.compile(r"[0-9]{4}(-[0-9]{2}(-[0-9]{2})?)?")
# Only YYYY-MM-DD: stored dates are compared with it as text.
_DATE: Final = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_TEXT_KINDS: Final = frozenset(
    {"text", "url", "email", "phone", "longtext", "choice", "multichoice"}
)


def _meta(prop: object) -> Mapping[str, Any]:
    meta = prop.get(NAMESPACE) if isinstance(prop, Mapping) else None
    return meta if isinstance(meta, Mapping) else {}


def _find(
    schemas: Mapping[str, Mapping[str, Any]],
    type_slug: str,
    key: str,
    sub_key: str | None,
) -> tuple[Mapping[str, Any] | None, str | None]:
    """Return the live property, or None plus the reason it is gone."""
    schema = schemas.get(type_slug)
    if schema is None:
        return None, f"The item type '{type_slug}' no longer exists."
    properties = schema.get("properties")
    prop = properties.get(key) if isinstance(properties, Mapping) else None
    if not isinstance(prop, Mapping) or _meta(prop).get("archived") is True:
        return None, f"The field '{key}' no longer exists on '{type_slug}'."
    if sub_key is None:
        return prop, None
    items = prop.get("items")
    inner = items.get("properties") if isinstance(items, Mapping) else None
    sub = inner.get(sub_key) if isinstance(inner, Mapping) else None
    if not isinstance(sub, Mapping) or _meta(sub).get("archived") is True:
        return None, f"The column '{sub_key}' no longer exists on '{key}'."
    return sub, None


def _is_number(operand: Operand) -> bool:
    return isinstance(operand, int | float) and not isinstance(operand, bool)


def _is_date(operand: Operand) -> bool:
    if not isinstance(operand, str) or _DATE.fullmatch(operand) is None:
        return False
    try:
        date.fromisoformat(operand)
    except ValueError:
        return False
    return True


def _is_partial_date(operand: Operand) -> bool:
    return isinstance(operand, str) and _PARTIAL_DATE.fullmatch(operand) is not None


def _is_text(operand: Operand) -> bool:
    return isinstance(operand, str)


_CHECKS: Final[Mapping[str, Callable[[Operand], bool]]] = {
    **dict.fromkeys(("number", "duration", "rating"), _is_number),
    **dict.fromkeys(_TEXT_KINDS, _is_text),
    "money": lambda operand: isinstance(operand, Money),
    "date": _is_date,
    "partialdate": _is_partial_date,
    "boolean": lambda operand: isinstance(operand, bool),
}


def _fits(kind: str, operand: Operand) -> bool:
    if isinstance(operand, RelativeDate):
        return kind in {"date", "partialdate"}
    check = _CHECKS.get(kind)
    return check is not None and check(operand)


def _operands(value: Operand | None) -> tuple[Operand, ...]:
    if value is None:
        return ()
    return value if isinstance(value, tuple) else (value,)


type _Schemas = Mapping[str, Mapping[str, Any]]


def _check_reference(
    schemas: _Schemas,
    warnings: list[QueryWarning],
    condition: FieldCondition,
    ref: FieldReference,
    kind: str,
    path: str,
) -> bool:
    """Check a field reference; return True when its target is gone."""
    if kind not in REF_KINDS or condition.sub_key is not None or condition.type is None:
        raise InvalidQueryError(
            f"A {kind} field cannot be compared with another field.", path=path
        )
    target, gone = _find(schemas, condition.type, ref.key, None)
    if target is None:
        warnings.append(QueryWarning(path, gone or ""))
        return True
    if kind_of(target) != kind:
        raise InvalidQueryError(
            f"'{ref.key}' is not a {kind} field, so it cannot be compared.",
            path=path,
        )
    return False


def _check_value(
    schemas: _Schemas,
    warnings: list[QueryWarning],
    condition: FieldCondition,
    kind: str,
    path: str,
) -> bool:
    """Check the operands; return True when a field reference is stale."""
    if condition.op in NO_VALUE_OPERATORS:
        return False
    stale = False
    for operand in _operands(condition.value):
        if isinstance(operand, FieldReference):
            stale |= _check_reference(schemas, warnings, condition, operand, kind, path)
        elif not _fits(kind, operand):
            raise InvalidQueryError(
                f"That value does not fit a {kind} field.", path=path
            )
    return stale


def _resolve_field(
    schemas: _Schemas,
    kinds: dict[FieldKey, str],
    warnings: list[QueryWarning],
    condition: FieldCondition,
    path: str,
) -> bool:
    """Record the field's kind; return True when the condition is stale."""
    if condition.type is None:
        # Per-item: the condition names its kind, so no schema is consulted.
        kind = condition.field_kind or ""
        if kind not in KIND_OPERATORS:
            raise InvalidQueryError("Unknown field kind.", path=path)
    else:
        prop, gone = _find(schemas, condition.type, condition.key, condition.sub_key)
        if prop is None:
            warnings.append(QueryWarning(path, gone or ""))
            return True
        found = kind_of(prop)
        if found is None:
            raise InvalidQueryError(
                f"The field '{condition.key}' cannot be filtered.", path=path
            )
        kind = found
    if condition.op not in KIND_OPERATORS[kind]:
        raise InvalidQueryError(
            f"'{condition.op}' is not available for {kind} fields.", path=path
        )
    if _check_value(schemas, warnings, condition, kind, path):
        return True
    if condition.type is None:
        return False
    kinds[(condition.type, condition.key, condition.sub_key)] = kind
    return False


def _check_date_condition(condition: DateCondition, path: str) -> None:
    for operand in _operands(condition.value):
        if not _fits("date", operand):
            raise InvalidQueryError("That is not a date.", path=path)


def _resolve_sort(
    schemas: _Schemas,
    kinds: dict[FieldKey, str],
    warnings: list[QueryWarning],
    index: int,
    type_slug: str,
    key: str,
) -> None:
    path = f"sort[{index}]"
    prop, gone = _find(schemas, type_slug, key, None)
    if prop is None:
        warnings.append(QueryWarning(path, gone or ""))
        return
    kind = kind_of(prop)
    if kind not in SORTABLE_KINDS:
        raise InvalidQueryError(f"The field '{key}' cannot be sorted on.", path=path)
    kinds[(type_slug, key, None)] = kind


def resolve_fields(query: Query, schemas: _Schemas) -> FieldResolution:
    """Resolve every field the query names against `schemas` (slug to schema).

    Raises:
        InvalidQueryError: For an operator or value that does not fit a field
            that exists. Fields that are gone become warnings.
    """
    kinds: dict[FieldKey, str] = {}
    warnings: list[QueryWarning] = []
    stale: set[FieldCondition] = set()
    for path, condition in walk_conditions(query.where):
        if isinstance(condition, FieldCondition):
            if _resolve_field(schemas, kinds, warnings, condition, path):
                stale.add(condition)
        elif isinstance(condition, DateCondition):
            _check_date_condition(condition, path)
    for index, key in enumerate(query.sort):
        if key.by == "field" and key.type and key.key:
            _resolve_sort(schemas, kinds, warnings, index, key.type, key.key)
    return FieldResolution(kinds=kinds, warnings=warnings, stale=frozenset(stale))


@dataclass(frozen=True)
class ConnectionReferences:
    """The relationship slugs and target items connection conditions name."""

    slugs: frozenset[str]
    items: frozenset[uuid.UUID]


@dataclass(frozen=True)
class ConnectionResolution:
    """Live relationships and visible target items, and what went stale."""

    relationships: Mapping[str, RelationshipInfo]
    visible_items: frozenset[uuid.UUID]
    warnings: list[QueryWarning]


def connection_references(group: Group | None) -> ConnectionReferences:
    """Collect what every connection condition under `group` names."""
    slugs: set[str] = set()
    items: set[uuid.UUID] = set()
    for _, condition in walk_conditions(group):
        if isinstance(condition, ConnectionCondition):
            if condition.relationship is not None:
                slugs.add(condition.relationship)
            if condition.item is not None:
                items.add(condition.item)
    return ConnectionReferences(slugs=frozenset(slugs), items=frozenset(items))


def resolve_connections(
    group: Group | None,
    *,
    directional: Mapping[str, bool],
    visible: Collection[uuid.UUID],
) -> ConnectionResolution:
    """Check connection conditions against live relationship types and items.

    `directional` maps each live relationship slug to its direction flag and
    `visible` holds the target items that exist in scope. A condition naming
    anything else warns and, being absent from the result, matches nothing.
    """
    relationships: dict[str, RelationshipInfo] = {}
    seen: set[uuid.UUID] = set()
    warnings: list[QueryWarning] = []
    for path, condition in walk_conditions(group):
        if not isinstance(condition, ConnectionCondition):
            continue
        slug = condition.relationship
        if slug is not None:
            if slug in directional:
                relationships[slug] = RelationshipInfo(
                    slug=slug, directional=directional[slug]
                )
            else:
                warnings.append(
                    QueryWarning(path, f"The relationship '{slug}' no longer exists.")
                )
        if condition.item is not None:
            if condition.item in visible:
                seen.add(condition.item)
            else:
                warnings.append(QueryWarning(path, "That item no longer exists."))
    return ConnectionResolution(
        relationships=relationships,
        visible_items=frozenset(seen),
        warnings=warnings,
    )
