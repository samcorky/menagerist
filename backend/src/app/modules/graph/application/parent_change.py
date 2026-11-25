"""Planning what attaching a type to a parent, or detaching it, does to its fields.

A subtype uses its parent's fields as well as its own (`effective_schema`), so giving a
type a parent can make two definitions of one key meet, and taking a parent away makes
the type lose the fields it inherited. This works out the answer from the schemas alone,
without touching anything, so the same result can be previewed and then applied.

- **Attaching.** A key both define with the same kind of field can be *merged*: the
  parent's definition is used, its choices widened to every option either side lists, so
  no stored value stops being one. A key defined as different kinds blocks the change.
- **Detaching.** The type either *keeps* the parent's fields (copied onto it, with the
  settings they carried) or *drops* them (archived, so values stay and can be restored).
- **Moving** is a detach and then an attach.

Items store their values by key, so none of this changes an item.
"""

import copy
from dataclasses import dataclass
from typing import Any, Literal

from app.modules.graph.application.field_definitions import (
    field_kind,
    forget_fields,
    with_every_option,
)
from app.modules.graph.application.schema_meta import NAMESPACE, effective_schema

type OnClash = Literal["refuse", "merge"]
type OnDetach = Literal["keep", "drop"]


@dataclass(frozen=True)
class ParentChange:
    """What to do when attaching meets a clash and when detaching loses fields."""

    on_clash: OnClash = "refuse"
    on_detach: OnDetach = "keep"


@dataclass(frozen=True, eq=False)
class ParentChangeResult:
    """What a parent change would do.

    `own_schema` is the type's schema afterwards and `parent_schema` the new parent's,
    or `None` when its fields do not change. `clashes` are the keys both define,
    `merged` those merged into the parent's definition, `conflicts` those defined as
    different kinds, and `blocked_by` the keys that stop the change. `kept` and
    `archived` are the old parent's keys copied onto the type or archived on it.
    """

    own_schema: dict[str, Any] | None
    parent_schema: dict[str, Any] | None
    clashes: tuple[str, ...] = ()
    merged: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    blocked_by: tuple[str, ...] = ()
    kept: tuple[str, ...] = ()
    archived: tuple[str, ...] = ()


def plan_parent_change(
    *,
    old_slug: str | None,
    old_parent: dict[str, Any] | None,
    new_slug: str | None,
    new_parent: dict[str, Any] | None,
    own: dict[str, Any] | None,
    change: ParentChange,
) -> ParentChangeResult:
    """Work out the effect of moving a type from `old_slug`'s parent to `new_slug`'s.

    Pure: neither schema is changed, and a blocked change still returns its result.
    Naming the parent the type already has is no change.
    """
    schema = copy.deepcopy(own)
    kept: tuple[str, ...] = ()
    archived: tuple[str, ...] = ()
    if old_slug is not None and old_parent is not None and old_slug != new_slug:
        if change.on_detach == "keep":
            schema = effective_schema(old_parent, schema)
            kept = tuple(_props(old_parent))
        else:
            schema, archived = _archive(old_parent, schema)

    parent_schema: dict[str, Any] | None = None
    clashes: tuple[str, ...] = ()
    merged: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    if new_slug is not None and new_parent is not None and new_slug != old_slug:
        own_props = _props(schema)
        new_props = _props(new_parent)
        clashes = tuple(key for key in own_props if key in new_props)
        conflicts = tuple(
            key
            for key in clashes
            if field_kind(own_props[key]) != field_kind(new_props[key])
        )
        if change.on_clash == "merge" and clashes and not conflicts:
            schema, parent_schema = _merge(schema, new_parent, clashes)
            merged = clashes
    blocked_by = conflicts if change.on_clash == "merge" else clashes
    return ParentChangeResult(
        own_schema=schema,
        parent_schema=parent_schema,
        clashes=clashes,
        merged=merged,
        conflicts=conflicts,
        blocked_by=blocked_by,
        kept=kept,
        archived=archived,
    )


def _props(schema: dict[str, Any] | None) -> dict[str, Any]:
    properties = (schema or {}).get("properties")
    return properties if isinstance(properties, dict) else {}


def _archive(
    parent: dict[str, Any], schema: dict[str, Any] | None
) -> tuple[dict[str, Any], tuple[str, ...]]:
    """`schema` with the parent's fields it lacks added as archived ones."""
    result = schema if schema is not None else {"type": "object", "properties": {}}
    properties = dict(_props(result))
    archived: list[str] = []
    for key, prop in _props(parent).items():
        if key in properties:
            continue
        hidden = copy.deepcopy(prop)
        hidden[NAMESPACE] = {**(hidden.get(NAMESPACE) or {}), "archived": True}
        properties[key] = hidden
        archived.append(key)
    result["properties"] = properties
    return result, tuple(archived)


def _merge(
    own: dict[str, Any] | None, parent: dict[str, Any], keys: tuple[str, ...]
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Drop `keys` from `own` and widen their choices on `parent`.

    The parent's schema comes back only if its fields changed.
    """
    widened = copy.deepcopy(parent)
    widened_props = widened["properties"]
    own_props = _props(own)
    for key in keys:
        widened_props[key] = with_every_option(
            widened_props[key], [widened_props[key], own_props[key]]
        )
    remaining = copy.deepcopy(own) or {}
    for key in keys:
        remaining["properties"].pop(key, None)
    forget_fields(remaining, set(keys))
    return remaining, (widened if widened != parent else None)
