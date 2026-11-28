"""Expand field conditions that reach across item types into per-type leaves.

A `field_kind` condition names a key and kind on any item, and an `origin`
condition names every type field copied from one saved field. Both become an
`or` of ordinary one-type leaves, found in the schemas each time the query runs,
so a type added after a smart collection was saved is matched without re-saving
it. A `field_kind` condition without a column also keeps itself as a leaf for
the item's own overlay. A condition that matches no field is left as it is and
resolves as stale without a warning: a later type may match it.
"""

from collections.abc import Iterator, Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from app.modules.graph.application.field_kinds import KIND_OPERATORS, kind_of
from app.modules.graph.application.query_resolution import accepts
from app.modules.graph.application.schema_meta import NAMESPACE
from app.modules.graph.domain.query import (
    ConnectionCondition,
    FieldCondition,
    Group,
    InvalidQueryError,
)

if TYPE_CHECKING:
    from app.modules.graph.domain.query import Condition

type _Schemas = Mapping[str, Mapping[str, Any]]


def _meta(prop: object) -> Mapping[str, Any]:
    meta = prop.get(NAMESPACE) if isinstance(prop, Mapping) else None
    return meta if isinstance(meta, Mapping) else {}


def _live(props: object) -> Iterator[tuple[str, Mapping[str, Any]]]:
    """The non-archived properties of a schema's or a table's `properties`."""
    if not isinstance(props, Mapping):
        return
    for key, prop in props.items():
        if isinstance(prop, Mapping) and _meta(prop).get("archived") is not True:
            yield key, prop


def _column(prop: Mapping[str, Any], sub_key: str) -> Mapping[str, Any] | None:
    items = prop.get("items")
    columns = items.get("properties") if isinstance(items, Mapping) else None
    return dict(_live(columns)).get(sub_key)


def _targets(
    schemas: _Schemas, condition: FieldCondition
) -> Iterator[tuple[str, str, str]]:
    """Yield (type, key, kind) for every live type field the condition reaches."""
    for slug, schema in schemas.items():
        for key, prop in _live(schema.get("properties")):
            if condition.origin is not None:
                origin = _meta(prop).get("origin")
                if not isinstance(origin, Mapping):
                    continue
                if origin.get("preset") != condition.origin:
                    continue
            elif key != condition.key:
                continue
            target = (
                prop if condition.sub_key is None else _column(prop, condition.sub_key)
            )
            kind = None if target is None else kind_of(target)
            if kind is not None:
                yield slug, key, kind


def fields_reached(
    schemas: _Schemas, *, key: str | None = None, origin: str | None = None
) -> Iterator[tuple[str, str, str]]:
    """Yield (type, key, kind) for each live type field with `key`, or from `origin`.

    The fields a condition or a measure that names a key, or a saved field, reaches.
    """
    yield from _targets(schemas, FieldCondition(key=key or "", op="=", origin=origin))


def _expand(
    condition: FieldCondition, schemas: _Schemas, path: str
) -> Group | Condition:
    if condition.field_kind is not None:
        if condition.field_kind not in KIND_OPERATORS:
            raise InvalidQueryError("Unknown field kind.", path=path)
        if not accepts(condition.field_kind, condition.op, condition.value):
            msg = f"That does not fit a {condition.field_kind} field."
            raise InvalidQueryError(msg, path=path)
    found = [
        (slug, key, kind)
        for slug, key, kind in _targets(schemas, condition)
        if condition.field_kind in {None, kind}
    ]
    usable = [t for t in found if accepts(t[2], condition.op, condition.value)]
    if found and not usable:
        raise InvalidQueryError("That does not fit this saved field.", path=path)
    leaves: list[Group | Condition] = [
        replace(condition, type=slug, key=key, field_kind=None, origin=None)
        for slug, key, _ in usable
    ]
    if condition.field_kind is not None and condition.sub_key is None:
        leaves.append(condition)
    if not leaves:
        return condition
    return Group(op="or", children=tuple(leaves))


def _group(group: Group, schemas: _Schemas, path: str) -> Group:
    children: list[Group | Condition] = []
    for index, child in enumerate(group.children):
        child_path = f"{path}.children[{index}]"
        if isinstance(child, Group):
            children.append(_group(child, schemas, child_path))
        elif isinstance(child, FieldCondition) and child.type is None:
            children.append(_expand(child, schemas, child_path))
        elif isinstance(child, ConnectionCondition) and child.where is not None:
            inner = _group(child.where, schemas, f"{child_path}.where")
            children.append(replace(child, where=inner))
        else:
            children.append(child)
    return replace(group, children=tuple(children))


def expand_field_scopes(where: Group | None, schemas: _Schemas) -> Group | None:
    """Rewrite every `field_kind` and `origin` condition under `where`.

    Raises:
        InvalidQueryError: For an unknown field kind, or an operator or value
            that fits none of the fields the condition reaches.
    """
    return None if where is None else _group(where, schemas, "where")
