"""What counts as the same field, and how two definitions of it combine.

Shared by promoting a per-item field to its type and by attaching a type to a parent:
the same field means the same key and kind, and a choice field's options are combined
so that no stored value stops being one of them.
"""

from typing import TYPE_CHECKING, Any

from app.modules.graph.application.field_kinds import kind_of
from app.modules.graph.application.schema_meta import NAMESPACE

if TYPE_CHECKING:
    from collections.abc import Callable


def field_kind(prop: dict[str, Any]) -> str | None:
    """The field's kind: the recorded one, else what its JSON Schema shape says."""
    meta = prop.get(NAMESPACE)
    explicit = meta.get("kind") if isinstance(meta, dict) else None
    if isinstance(explicit, str):
        return explicit
    declared = prop.get("type")
    return kind_of(prop) or (declared if isinstance(declared, str) else None)


def with_every_option(
    chosen: dict[str, Any], definitions: list[dict[str, Any]]
) -> dict[str, Any]:
    """`chosen` with its choices widened to every option the definitions list."""
    if isinstance(chosen.get("enum"), list):
        return {**chosen, "enum": _union(chosen["enum"], definitions, _direct)}
    items = chosen.get("items")
    if isinstance(items, dict) and isinstance(items.get("enum"), list):
        widened = {**items, "enum": _union(items["enum"], definitions, _nested)}
        return {**chosen, "items": widened}
    return chosen


def forget_fields(schema: dict[str, Any], keys: set[str]) -> None:
    """Remove `keys` from the schema's required lists and its layout, in place.

    The properties are left to the caller. A section in the layout stays even when
    emptied, since it is the person's.
    """
    root_required = schema.get("required")
    if isinstance(root_required, list):
        schema["required"] = [k for k in root_required if k not in keys]
        if not schema["required"]:
            del schema["required"]
    meta = schema.get(NAMESPACE)
    if not isinstance(meta, dict):
        return
    required = meta.get("required")
    if isinstance(required, list):
        meta["required"] = [k for k in required if k not in keys]
        if not meta["required"]:
            del meta["required"]
    layout = meta.get("layout")
    if isinstance(layout, list):
        meta["layout"] = _prune(layout, keys)


def _prune(items: list[Any], keys: set[str]) -> list[Any]:
    pruned: list[Any] = []
    for item in items:
        if isinstance(item, dict) and item.get("key") in keys:
            continue
        if isinstance(item, dict) and isinstance(item.get("items"), list):
            item = {**item, "items": _prune(item["items"], keys)}
        pruned.append(item)
    return pruned


def _direct(prop: dict[str, Any]) -> object:
    return prop.get("enum")


def _nested(prop: dict[str, Any]) -> object:
    items = prop.get("items")
    return items.get("enum") if isinstance(items, dict) else None


def _union(
    first: list[Any],
    definitions: list[dict[str, Any]],
    options_of: Callable[[dict[str, Any]], object],
) -> list[Any]:
    combined = list(first)
    for definition in definitions:
        options = options_of(definition)
        if isinstance(options, list):
            combined.extend(o for o in options if o not in combined)
    return combined
