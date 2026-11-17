"""Read an item type's schema as the fields an import fills, and check values."""

from typing import TYPE_CHECKING, Any

from app.modules.graph.application._validate_attributes import validate_attributes
from app.modules.graph.application.field_kinds import kind_of
from app.modules.graph.application.schema_meta import NAMESPACE, archived_keys
from app.modules.graph.domain.errors import InvalidAttributesError
from app.modules.transfer.domain.tabular import FieldSpec

if TYPE_CHECKING:
    from collections.abc import Mapping

# Kinds whose stored value is not plain text, a number, yes/no or a date.
_NOT_YET = frozenset(
    {"money", "duration", "quantity", "list", "checklist", "group", "cron", "opaque"}
)


def field_specs(schema: Mapping[str, Any]) -> list[FieldSpec]:
    """Describe each live property of an item type's resolved schema."""
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return []
    archived = archived_keys(dict(schema))
    return [
        _spec(key, prop)
        for key, prop in properties.items()
        if key not in archived and isinstance(prop, dict)
    ]


def _spec(key: str, prop: Mapping[str, Any]) -> FieldSpec:
    title = prop.get("title")
    title = title if isinstance(title, str) and title else key
    meta = prop.get(NAMESPACE)
    explicit = meta.get("kind") if isinstance(meta, dict) else None
    kind = explicit if isinstance(explicit, str) else kind_of(prop)
    declared = prop.get("type")
    json_type = declared if isinstance(declared, str) else None
    options, multiple = _options(prop)
    importable = kind not in _NOT_YET and json_type != "object"
    return FieldSpec(
        key=key,
        title=title,
        json_type=json_type,
        kind=kind,
        options=options,
        multiple=multiple,
        importable=importable,
        reason=None if importable else f"{title} cannot be imported yet",
    )


def _options(prop: Mapping[str, Any]) -> tuple[tuple[str, ...] | None, bool]:
    """Return the allowed choices, and whether a value may hold several."""
    direct = prop.get("enum")
    if isinstance(direct, list) and all(isinstance(o, str) for o in direct):
        return tuple(direct), False
    items = prop.get("items")
    if prop.get("type") == "array" and isinstance(items, dict):
        listed = items.get("enum")
        if isinstance(listed, list) and all(isinstance(o, str) for o in listed):
            return tuple(listed), True
    return None, False


def attribute_problems(
    schema: dict[str, Any], attributes: Mapping[str, Any]
) -> list[str]:
    """Return a message per value that breaks the schema, led by the field's title."""
    try:
        validate_attributes(schema, dict(attributes))
    except InvalidAttributesError as error:
        titles = {spec.key: spec.title for spec in field_specs(schema)}
        return [_problem(titles, entry) for entry in error.validation_errors]
    return []


def _problem(titles: Mapping[str, str], entry: Mapping[str, Any]) -> str:
    key = str(entry["path"]).lstrip("/").split("/")[0]
    message = str(entry["message"])
    return f"{titles[key]}: {message}" if key in titles else message
