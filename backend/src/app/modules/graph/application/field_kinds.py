"""Which operators each field kind supports, and how a property's kind is read."""

from collections.abc import Mapping
from typing import Any, Final

from app.modules.graph.application.schema_meta import NAMESPACE

_ORDERED = frozenset({"=", "!=", ">", ">=", "<", "<=", "between", "empty", "not_empty"})
_TEXT = frozenset({"=", "!=", "~", "in", "empty", "not_empty"})

KIND_OPERATORS: Final[Mapping[str, frozenset[str]]] = {
    "text": _TEXT,
    "url": _TEXT,
    "email": _TEXT,
    "phone": _TEXT,
    "longtext": frozenset({"~", "empty", "not_empty"}),
    "number": _ORDERED,
    "duration": _ORDERED,
    "rating": _ORDERED,
    "money": _ORDERED,
    "date": _ORDERED,
    "partialdate": _ORDERED,
    "boolean": frozenset({"=", "!="}),
    "choice": frozenset({"=", "!=", "in", "empty", "not_empty"}),
    "multichoice": frozenset({"has", "empty", "not_empty"}),
    "checklist": frozenset({"incomplete", "complete", "empty", "not_empty"}),
}

# Kinds whose conditions may compare with another field of the same kind.
REF_KINDS: Final = frozenset({"number", "duration", "rating", "money", "date"})
NO_VALUE_OPERATORS: Final = frozenset({"empty", "not_empty", "incomplete", "complete"})


def kind_of(prop: Mapping[str, Any]) -> str | None:
    """Return the filterable kind of a schema property, or None if it has none.

    An explicit `x-menagerist.kind` wins when it is filterable. Otherwise the
    kind is inferred from the JSON Schema shape, as the frontend does.
    """
    meta = prop.get(NAMESPACE)
    explicit = meta.get("kind") if isinstance(meta, Mapping) else None
    if isinstance(explicit, str) and explicit in KIND_OPERATORS:
        return explicit
    if isinstance(explicit, str) and explicit in {
        "opaque",
        "group",
        "list",
        "quantity",
    }:
        return None
    return _infer_kind(prop)


def _infer_kind(prop: Mapping[str, Any]) -> str | None:
    """Infer a kind from the JSON Schema shape alone."""
    declared = prop.get("type")
    if declared == "string":
        if prop.get("format") == "date":
            return "date"
        return "choice" if "enum" in prop else "text"
    if declared in {"number", "integer"}:
        return "number"
    if declared == "boolean":
        return "boolean"
    if declared == "array":
        items = prop.get("items")
        if (
            isinstance(items, Mapping)
            and items.get("type") == "string"
            and "enum" in items
        ):
            return "multichoice"
    return None
