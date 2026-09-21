"""Reader for the `x-menagerist` metadata namespace in attribute schemas.

Standard JSON Schema keywords describe validation; `x-menagerist` describes
everything else (layout, advisory `required`, archived fields, display hints).
Nothing else in the backend reads `x-*` keywords directly.
"""

from typing import Any

from app.modules.graph.domain.errors import InvalidSchemaError

NAMESPACE = "x-menagerist"

_PROPERTY_BOOL_MEMBERS = ("archived", "search", "suggest")
_PROPERTY_STR_MEMBERS = ("kind", "display")
MAX_CARD_HIGHLIGHTS = 3


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


def _check_property_meta(path: str, prop: object) -> None:
    meta = prop.get(NAMESPACE) if isinstance(prop, dict) else None
    if meta is None:
        return
    if not isinstance(meta, dict):
        raise InvalidSchemaError(f"{path}/{NAMESPACE} must be an object")
    for member in _PROPERTY_STR_MEMBERS:
        if member in meta and not isinstance(meta[member], str):
            raise InvalidSchemaError(f"{path}/{NAMESPACE}/{member} must be a string")
    for member in _PROPERTY_BOOL_MEMBERS:
        if member in meta and not isinstance(meta[member], bool):
            raise InvalidSchemaError(f"{path}/{NAMESPACE}/{member} must be a boolean")
    if "config" in meta and not isinstance(meta["config"], dict):
        raise InvalidSchemaError(f"{path}/{NAMESPACE}/config must be an object")


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
    entry: object, props: dict[str, Any], seen: set[str]
) -> None:
    key = entry.get("key") if isinstance(entry, dict) else None
    if not isinstance(key, str):
        raise InvalidSchemaError(
            f"{NAMESPACE}/highlights/card entries need a string key"
        )
    if key in seen:
        raise InvalidSchemaError(f"{NAMESPACE}/highlights/card repeats {key!r}")
    seen.add(key)
    if key not in props:
        raise InvalidSchemaError(
            f"{NAMESPACE}/highlights/card refers to unknown field {key!r}"
        )
    if _meta(props[key]).get("archived") is True:
        raise InvalidSchemaError(
            f"{NAMESPACE}/highlights/card refers to archived field {key!r}"
        )


def _check_highlights(root: object, properties: object) -> None:
    """Check `highlights.card`: at most 3 unique keys of existing, live properties."""
    highlights = root.get("highlights") if isinstance(root, dict) else None
    if highlights is None:
        return
    if not isinstance(highlights, dict):
        raise InvalidSchemaError(f"{NAMESPACE}/highlights must be an object")
    card = highlights.get("card")
    if card is None:
        return
    if not isinstance(card, list):
        raise InvalidSchemaError(f"{NAMESPACE}/highlights/card must be an array")
    if len(card) > MAX_CARD_HIGHLIGHTS:
        raise InvalidSchemaError(
            f"{NAMESPACE}/highlights/card allows at most {MAX_CARD_HIGHLIGHTS} fields"
        )
    props = properties if isinstance(properties, dict) else {}
    seen: set[str] = set()
    for entry in card:
        _check_highlight_entry(entry, props, seen)


def check_meta_shape(schema: dict[str, Any]) -> None:
    """Check that known `x-menagerist` members are correctly typed.

    Unknown members are allowed so newer clients stay forward compatible.

    :raises InvalidSchemaError: when a known member has the wrong type or a
        highlight refers to a missing or archived field.
    """
    _check_root_meta(schema.get(NAMESPACE))
    properties = schema.get("properties")
    _check_highlights(schema.get(NAMESPACE), properties)
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
