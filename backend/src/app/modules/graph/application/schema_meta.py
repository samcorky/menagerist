"""Reader for the `x-menagerist` metadata namespace in attribute schemas.

Standard JSON Schema keywords describe validation; `x-menagerist` describes
everything else (layout, advisory `required`, archived fields, display hints).
Nothing else in the backend reads `x-*` keywords directly.
"""

import copy
from typing import Any

import jsonschema

from app.modules.graph.domain.errors import InvalidSchemaError

NAMESPACE = "x-menagerist"

_PROPERTY_BOOL_MEMBERS = (
    "archived",
    "search",
    "suggest",
    "multiline",
    "capture",
    "barcode",
)
_PROPERTY_STR_MEMBERS = ("kind", "display")
MAX_CARD_HIGHLIGHTS = 3
MAX_CONNECTION_HIGHLIGHTS = 2
_HIGHLIGHT_LIMITS = {
    "card": MAX_CARD_HIGHLIGHTS,
    "connection": MAX_CONNECTION_HIGHLIGHTS,
}
# Kinds whose values are not free text (frontend descriptors: `searchable: false`).
NON_SEARCHABLE_KINDS = frozenset({"rating"})


def _meta(node: object) -> dict[str, Any]:
    """Return the `x-menagerist` object of a schema or property, or `{}`."""
    if not isinstance(node, dict):
        return {}
    meta = node.get(NAMESPACE)
    return meta if isinstance(meta, dict) else {}


def required_keys(schema: dict[str, Any]) -> list[str]:
    """Return the keys marked required. Advisory only: never validated."""
    required = _meta(schema).get("required")
    if not isinstance(required, list):
        return []
    return [key for key in required if isinstance(key, str)]


def archived_keys(schema: dict[str, Any]) -> set[str]:
    """Return the keys of top-level properties marked archived."""
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return set()
    return {
        key for key, prop in properties.items() if _meta(prop).get("archived") is True
    }


def search_excluded_keys(schema: dict[str, Any]) -> list[str]:
    """Return top-level keys whose values attribute search must skip.

    Archived fields (hidden from users), fields marked `search: false`, and
    non-searchable kinds such as ratings.
    """
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return []
    excluded: list[str] = []
    for key, prop in properties.items():
        meta = _meta(prop)
        if (
            meta.get("archived") is True
            or meta.get("search") is False
            or meta.get("kind") in NON_SEARCHABLE_KINDS
        ):
            excluded.append(key)
    return excluded


def check_schema_definition(schema: dict[str, Any]) -> None:
    """Check that `schema` is valid JSON Schema with a well-shaped `x-menagerist`.

    Used wherever a schema is authored: node types, edge types and a node's
    `extra_schema` overlay.

    :raises InvalidSchemaError: on either problem.
    """
    try:
        jsonschema.validators.validator_for(schema).check_schema(schema)
    except jsonschema.SchemaError as exc:
        raise InvalidSchemaError(str(exc.message)) from exc
    check_meta_shape(schema)


def merge_attribute_schemas(
    type_schema: dict[str, Any] | None, extra_schema: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Combine a node type's schema with a node's per-item overlay (WI-19d).

    Both describe properties of the same `attributes` dict, so validation needs
    one merged schema. `required` and `layout` are concatenated (type fields
    first); `highlights` stays type-only and is not merged. Returns `None`
    when neither schema is given.

    :raises InvalidSchemaError: when a key is defined by both schemas.
    """
    if type_schema is None and extra_schema is None:
        return None
    type_props = type_schema.get("properties") if type_schema else None
    extra_props = extra_schema.get("properties") if extra_schema else None
    type_props = type_props if isinstance(type_props, dict) else {}
    extra_props = extra_props if isinstance(extra_props, dict) else {}
    overlap = set(type_props) & set(extra_props)
    if overlap:
        raise InvalidSchemaError(
            "extra_schema redefines field(s) already on the item type: "
            + ", ".join(sorted(overlap))
        )
    merged: dict[str, Any] = {
        "type": "object",
        "properties": {**type_props, **extra_props},
    }
    type_meta = _meta(type_schema)
    extra_meta = _meta(extra_schema)
    required = [*type_meta.get("required", []), *extra_meta.get("required", [])]
    layout = [*type_meta.get("layout", []), *extra_meta.get("layout", [])]
    meta: dict[str, Any] = {}
    if required:
        meta["required"] = required
    if layout:
        meta["layout"] = layout
    if meta:
        merged[NAMESPACE] = meta
    return merged


def _dedupe(*lists: object) -> list[Any]:
    """The items of the lists in order, each once."""
    seen: list[Any] = []
    for items in lists:
        for item in items if isinstance(items, list) else []:
            if item not in seen:
                seen.append(item)
    return seen


def effective_schema(
    parent_schema: dict[str, Any] | None, own_schema: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Combine a parent type's schema with a subtype's own into what the subtype uses.

    An item always presents itself using its own type resolved with inheritance:
    the fields are the parent's then the subtype's, `required` is the union, the
    `layout` is the parent's sections then the subtype's, and an archived field
    stays archived (the flag is on the field). Each `highlights` list is the
    parent's unless the subtype sets one of its own, which replaces it, even when
    empty. Any other setting is the subtype's, else the parent's.

    A key both define keeps the parent's definition: the type rules refuse that, so
    this only guards stored data that predates them. Neither input is changed.
    """
    if parent_schema is None:
        return own_schema
    if own_schema is None:
        return copy.deepcopy(parent_schema)
    parent_props = parent_schema.get("properties")
    own_props = own_schema.get("properties")
    parent_props = parent_props if isinstance(parent_props, dict) else {}
    own_props = own_props if isinstance(own_props, dict) else {}
    merged: dict[str, Any] = {
        key: value
        for key, value in {**parent_schema, **own_schema}.items()
        if key not in ("properties", "required", NAMESPACE)
    }
    merged["properties"] = {
        **parent_props,
        **{k: v for k, v in own_props.items() if k not in parent_props},
    }
    required = _dedupe(parent_schema.get("required"), own_schema.get("required"))
    if required:
        merged["required"] = required
    meta = _effective_meta(_meta(parent_schema), _meta(own_schema))
    if meta:
        merged[NAMESPACE] = meta
    return copy.deepcopy(merged)


def _effective_meta(parent: dict[str, Any], own: dict[str, Any]) -> dict[str, Any]:
    """The `x-menagerist` block of `effective_schema`."""
    combined = {
        key: value
        for key, value in {**parent, **own}.items()
        if key not in ("required", "layout", "highlights")
    }
    required = _dedupe(parent.get("required"), own.get("required"))
    if required:
        combined["required"] = required
    layout = [*parent.get("layout", []), *own.get("layout", [])]
    if layout:
        combined["layout"] = layout
    highlights = {
        **(parent["highlights"] if isinstance(parent.get("highlights"), dict) else {}),
        **(own["highlights"] if isinstance(own.get("highlights"), dict) else {}),
    }
    if highlights:
        combined["highlights"] = highlights
    return combined


def validation_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of `schema` for validation.

    Drops the root `required` array and archived properties, so neither can
    reject a value. The stored schema is not modified.
    """
    archived = archived_keys(schema)
    stripped = {key: value for key, value in schema.items() if key != "required"}
    properties = schema.get("properties")
    if archived and isinstance(properties, dict):
        stripped["properties"] = {
            key: prop for key, prop in properties.items() if key not in archived
        }
    return stripped


def _check_property_meta_shape(path: str, meta: dict[str, Any]) -> None:
    for member in _PROPERTY_STR_MEMBERS:
        if member in meta and not isinstance(meta[member], str):
            raise InvalidSchemaError(f"{path}/{NAMESPACE}/{member} must be a string")
    for member in _PROPERTY_BOOL_MEMBERS:
        if member in meta and not isinstance(meta[member], bool):
            raise InvalidSchemaError(f"{path}/{NAMESPACE}/{member} must be a boolean")
    if "config" in meta and not isinstance(meta["config"], dict):
        raise InvalidSchemaError(f"{path}/{NAMESPACE}/config must be an object")
    if "columns" in meta:
        columns = meta["columns"]
        if not isinstance(columns, list) or not all(
            isinstance(c, str) for c in columns
        ):
            raise InvalidSchemaError(
                f"{path}/{NAMESPACE}/columns must be an array of strings"
            )


def _check_property_meta(path: str, prop: object) -> None:
    meta = prop.get(NAMESPACE) if isinstance(prop, dict) else None
    if meta is None:
        return
    if not isinstance(meta, dict):
        raise InvalidSchemaError(f"{path}/{NAMESPACE} must be an object")
    _check_property_meta_shape(path, meta)


def _check_root_meta(root: object) -> None:
    if root is None:
        return
    if not isinstance(root, dict):
        raise InvalidSchemaError(f"{NAMESPACE} must be an object")
    version = root.get("version")
    if "version" in root and (
        isinstance(version, bool) or not isinstance(version, int)
    ):
        raise InvalidSchemaError(f"{NAMESPACE}/version must be an integer")
    for member in ("layout", "required"):
        if member in root and not isinstance(root[member], list):
            raise InvalidSchemaError(f"{NAMESPACE}/{member} must be an array")
    if not all(isinstance(key, str) for key in root.get("required", [])):
        raise InvalidSchemaError(f"{NAMESPACE}/required must contain strings")


def _check_highlight_entry(
    name: str, entry: object, props: dict[str, Any], seen: set[str]
) -> None:
    where = f"{NAMESPACE}/highlights/{name}"
    if not isinstance(entry, dict):
        raise InvalidSchemaError(f"{where} entries need a string key")
    key = entry.get("key")
    if not isinstance(key, str):
        raise InvalidSchemaError(f"{where} entries need a string key")
    if key in seen:
        raise InvalidSchemaError(f"{where} repeats {key!r}")
    seen.add(key)
    if key not in props:
        raise InvalidSchemaError(f"{where} refers to unknown field {key!r}")
    if _meta(props[key]).get("archived") is True:
        raise InvalidSchemaError(f"{where} refers to archived field {key!r}")
    _check_highlight_column(where, key, entry.get("column"), props[key])


def _table_columns(prop: object) -> dict[str, Any] | None:
    """The sub-properties of a table (an array of objects), else `None`.

    A checklist is also an array of objects, but it carries its own `kind`.
    """
    if not isinstance(prop, dict) or _meta(prop).get("kind") not in (None, "group"):
        return None
    items = prop.get("items")
    if not isinstance(items, dict) or items.get("type") != "object":
        return None
    columns = items.get("properties")
    return columns if isinstance(columns, dict) else {}


def _check_highlight_column(where: str, key: str, column: object, prop: object) -> None:
    """A table is highlighted by one of its columns; no other field takes a column."""
    columns = _table_columns(prop)
    if columns is None:
        if column is not None:
            raise InvalidSchemaError(
                f"{where} gives a column for {key!r}, which is not a table"
            )
        return
    if not isinstance(column, str):
        raise InvalidSchemaError(f"{where} needs a column for the table {key!r}")
    if column not in columns:
        raise InvalidSchemaError(
            f"{where} refers to unknown column {column!r} of {key!r}"
        )


def _check_highlight_list(name: str, entries: object, properties: object) -> None:
    where = f"{NAMESPACE}/highlights/{name}"
    if not isinstance(entries, list):
        raise InvalidSchemaError(f"{where} must be an array")
    if len(entries) > _HIGHLIGHT_LIMITS[name]:
        raise InvalidSchemaError(
            f"{where} allows at most {_HIGHLIGHT_LIMITS[name]} fields"
        )
    props = properties if isinstance(properties, dict) else {}
    seen: set[str] = set()
    for entry in entries:
        _check_highlight_entry(name, entry, props, seen)


def _check_highlights(root: object, properties: object) -> None:
    """Check `highlights.card` (max 3) and `highlights.connection` (max 2).

    Each is a list of unique keys of existing, live properties; a table's entry
    also names one of its columns. Other lists
    are left alone.
    """
    highlights = root.get("highlights") if isinstance(root, dict) else None
    if highlights is None:
        return
    if not isinstance(highlights, dict):
        raise InvalidSchemaError(f"{NAMESPACE}/highlights must be an object")
    for name in _HIGHLIGHT_LIMITS:
        if highlights.get(name) is not None:
            _check_highlight_list(name, highlights[name], properties)


def check_meta_shape(
    schema: dict[str, Any], *, inherited: dict[str, Any] | None = None
) -> None:
    """Check that known `x-menagerist` members are correctly typed.

    Unknown members are allowed so newer clients stay forward compatible.
    `inherited` is a parent type's properties: a subtype may highlight one of them.

    :raises InvalidSchemaError: when a known member has the wrong type or a
        highlight refers to a missing or archived field.
    """
    _check_root_meta(schema.get(NAMESPACE))
    properties = schema.get("properties")
    own = properties if isinstance(properties, dict) else {}
    _check_highlights(
        schema.get(NAMESPACE), {**(inherited or {}), **own} if inherited else properties
    )
    if not isinstance(properties, dict):
        return
    for key, prop in properties.items():
        _check_property_meta(f"/properties/{key}", prop)
        items = prop.get("items") if isinstance(prop, dict) else None
        sub_properties = items.get("properties") if isinstance(items, dict) else None
        if isinstance(sub_properties, dict):
            for sub_key, sub_prop in sub_properties.items():
                path = f"/properties/{key}/items/properties/{sub_key}"
                _check_property_meta(path, sub_prop)
