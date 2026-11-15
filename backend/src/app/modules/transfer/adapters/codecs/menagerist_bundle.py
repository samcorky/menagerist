"""The `menagerist-bundle` file: Menagerist's own export and import format."""

from collections.abc import Mapping
from typing import Any

from app.modules.transfer.domain.bundle import (
    BUNDLE_FORMAT,
    BUNDLE_VERSION,
    PRESETS_ONLY_VERSION,
    REF_PATTERN,
    REF_RULE,
    TYPES_VERSION,
    Bundle,
    BundleCollection,
    BundleConnection,
    BundleItem,
    BundleItemType,
    BundlePreset,
    BundleRelationshipType,
    unportable_condition,
)
from app.modules.transfer.domain.errors import InvalidBundleError

_ENVELOPE = {"format", "version", "presets"}
_TYPE_SECTIONS = {"relationship_types", "item_types"}
_CONTENT_SECTIONS = {"items", "connections", "collections"}
_ITEM_REQUIRED = {"ref", "type_ref", "name"}
_ITEM_KEYS = _ITEM_REQUIRED | {"description", "attributes", "tags", "extra_schema"}
_CONNECTION_REQUIRED = {"source_ref", "target_ref", "type_ref"}
_CONNECTION_KEYS = _CONNECTION_REQUIRED | {"attributes"}
_COLLECTION_REQUIRED = {"ref", "name"}
_COLLECTION_KEYS = _COLLECTION_REQUIRED | {"description", "item_refs", "definition"}
_PRESET_REQUIRED = {"ref", "kind", "label", "definition"}
_PRESET_KEYS = _PRESET_REQUIRED | {"description"}
_TYPE_REQUIRED = {"ref", "slug", "label"}
_ITEM_TYPE_KEYS = _TYPE_REQUIRED | {
    "description",
    "attributes_schema",
    "icon",
    "colour",
}
_RELATIONSHIP_TYPE_KEYS = _TYPE_REQUIRED | {
    "description",
    "attributes_schema",
    "reverse_label",
    "directional",
}


def _text(value: object, what: str) -> str:
    if not isinstance(value, str):
        raise InvalidBundleError(f"{what} must be text")
    return value


def _optional_text(raw: Mapping[str, Any], key: str, where: str) -> str | None:
    value = raw.get(key)
    return None if value is None else _text(value, f"{where} {key}")


def _entry(
    raw: object, where: str, required: set[str], allowed: set[str]
) -> Mapping[str, Any]:
    """Check one entry's shape: an object with its required keys and no others."""
    if not isinstance(raw, Mapping):
        raise InvalidBundleError(f"{where} must be an object")
    missing = required - raw.keys()
    if missing:
        raise InvalidBundleError(f"{where} needs {', '.join(sorted(missing))}")
    unknown = raw.keys() - allowed
    if unknown:
        raise InvalidBundleError(f"{where} has unknown keys {sorted(unknown)}")
    ref = _text(raw["ref"], f"{where} ref")
    if not REF_PATTERN.match(ref):
        raise InvalidBundleError(f"{where} ref {REF_RULE}")
    return raw


def _preset(raw: object, n: int) -> BundlePreset:
    where = f"presets[{n}]"
    entry = _entry(raw, where, _PRESET_REQUIRED, _PRESET_KEYS)
    if not isinstance(entry["definition"], dict):
        raise InvalidBundleError(f"{where} definition must be an object")
    return BundlePreset(
        ref=entry["ref"],
        kind=_text(entry["kind"], f"{where} kind"),
        label=_text(entry["label"], f"{where} label"),
        description=_optional_text(entry, "description", where),
        definition=entry["definition"],
    )


def _schema(entry: Mapping[str, Any], where: str) -> dict[str, Any] | None:
    schema = entry.get("attributes_schema")
    if schema is not None and not isinstance(schema, dict):
        raise InvalidBundleError(f"{where} attributes_schema must be an object")
    return schema


def _item_type(raw: object, n: int) -> BundleItemType:
    where = f"item_types[{n}]"
    entry = _entry(raw, where, _TYPE_REQUIRED, _ITEM_TYPE_KEYS)
    return BundleItemType(
        ref=entry["ref"],
        slug=_text(entry["slug"], f"{where} slug"),
        label=_text(entry["label"], f"{where} label"),
        description=_optional_text(entry, "description", where),
        attributes_schema=_schema(entry, where),
        icon=_optional_text(entry, "icon", where),
        colour=_optional_text(entry, "colour", where),
    )


def _relationship_type(raw: object, n: int) -> BundleRelationshipType:
    where = f"relationship_types[{n}]"
    entry = _entry(raw, where, _TYPE_REQUIRED, _RELATIONSHIP_TYPE_KEYS)
    directional = entry.get("directional", True)
    if not isinstance(directional, bool):
        raise InvalidBundleError(f"{where} directional must be true or false")
    return BundleRelationshipType(
        ref=entry["ref"],
        slug=_text(entry["slug"], f"{where} slug"),
        label=_text(entry["label"], f"{where} label"),
        reverse_label=_optional_text(entry, "reverse_label", where),
        description=_optional_text(entry, "description", where),
        directional=directional,
        attributes_schema=_schema(entry, where),
    )


def _object(entry: Mapping[str, Any], key: str, where: str) -> dict[str, Any]:
    value = entry.get(key, {})
    if not isinstance(value, dict):
        raise InvalidBundleError(f"{where} {key} must be an object")
    return value


def _ref_text(entry: Mapping[str, Any], key: str, where: str) -> str:
    ref = _text(entry[key], f"{where} {key}")
    if not REF_PATTERN.match(ref):
        raise InvalidBundleError(f"{where} {key} {REF_RULE}")
    return ref


def _item(raw: object, n: int) -> BundleItem:
    where = f"items[{n}]"
    entry = _entry(raw, where, _ITEM_REQUIRED, _ITEM_KEYS)
    tags = entry.get("tags", [])
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        raise InvalidBundleError(f"{where} tags must be a list of text")
    return BundleItem(
        ref=entry["ref"],
        type_ref=_ref_text(entry, "type_ref", where),
        name=_text(entry["name"], f"{where} name"),
        description=_optional_text(entry, "description", where),
        attributes=_object(entry, "attributes", where),
        tags=tuple(tags),
        extra_schema=_schema_object(entry, "extra_schema", where),
    )


def _schema_object(
    entry: Mapping[str, Any], key: str, where: str
) -> dict[str, Any] | None:
    value = entry.get(key)
    if value is not None and not isinstance(value, dict):
        raise InvalidBundleError(f"{where} {key} must be an object")
    return value


def _connection(raw: object, n: int) -> BundleConnection:
    where = f"connections[{n}]"
    if not isinstance(raw, Mapping):
        raise InvalidBundleError(f"{where} must be an object")
    missing = _CONNECTION_REQUIRED - raw.keys()
    if missing:
        raise InvalidBundleError(f"{where} needs {', '.join(sorted(missing))}")
    unknown = raw.keys() - _CONNECTION_KEYS
    if unknown:
        raise InvalidBundleError(f"{where} has unknown keys {sorted(unknown)}")
    return BundleConnection(
        source_ref=_ref_text(raw, "source_ref", where),
        target_ref=_ref_text(raw, "target_ref", where),
        type_ref=_ref_text(raw, "type_ref", where),
        attributes=_object(raw, "attributes", where),
    )


def _collection(raw: object, n: int) -> BundleCollection:
    where = f"collections[{n}]"
    entry = _entry(raw, where, _COLLECTION_REQUIRED, _COLLECTION_KEYS)
    item_refs = entry.get("item_refs", [])
    if not isinstance(item_refs, list):
        raise InvalidBundleError(f"{where} item_refs must be a list")
    definition = _schema_object(entry, "definition", where)
    if (definition is None) == (not item_refs):
        raise InvalidBundleError(f"{where} needs either item_refs or a definition")
    if definition is not None:
        found = unportable_condition(definition)
        if found is not None:
            path, reason = found
            raise InvalidBundleError(f"{where} definition at '{path}': {reason}")
    return BundleCollection(
        ref=entry["ref"],
        name=_text(entry["name"], f"{where} name"),
        description=_optional_text(entry, "description", where),
        item_refs=tuple(_text(r, f"{where} item_refs") for r in item_refs),
        definition=definition,
    )


def _check_links(bundle: Bundle) -> None:
    """Refuse a file whose items, connections or collections name what it lacks."""
    item_types = {t.ref for t in bundle.item_types}
    for item in bundle.items:
        if item.type_ref not in item_types:
            raise InvalidBundleError(
                f"item '{item.ref}' has type '{item.type_ref}', not in the file"
            )
    items = {i.ref for i in bundle.items}
    _check_connections(bundle, items)
    for collection in bundle.collections:
        for ref in collection.item_refs:
            if ref not in items:
                raise InvalidBundleError(
                    f"collection '{collection.ref}' has item '{ref}', not in the file"
                )


def _check_connections(bundle: Bundle, items: set[str]) -> None:
    relationship_types = {t.ref for t in bundle.relationship_types}
    for c in bundle.connections:
        if c.type_ref not in relationship_types:
            raise InvalidBundleError(
                f"a connection has type '{c.type_ref}', not in the file"
            )
        if c.source_ref not in items or c.target_ref not in items:
            raise InvalidBundleError("a connection joins an item not in the file")
        if c.source_ref == c.target_ref:
            raise InvalidBundleError("a connection cannot join an item to itself")


def _section(data: Mapping[str, Any], key: str) -> list[Any]:
    section = data.get(key, [])
    if not isinstance(section, list):
        raise InvalidBundleError(f"{key} must be a list")
    return section


class MenageristBundleCodec:
    """Reads and writes `menagerist-bundle`: presets, and from version 2 types.

    Only the file's shape is checked here; whether each preset or type is a valid
    one is the owning module's call, made when the bundle is planned or applied.
    A type's fields name the presets they use as `{"$preset": ref}`.
    """

    format = BUNDLE_FORMAT

    def decode(self, data: Mapping[str, Any]) -> Bundle:
        """Read a parsed file into a bundle; unknown keys are refused.

        Raises:
            InvalidBundleError: the file is not a valid `menagerist-bundle`.
        """
        version = data.get("version")
        if version not in (PRESETS_ONLY_VERSION, TYPES_VERSION, BUNDLE_VERSION):
            raise InvalidBundleError(f"unsupported {BUNDLE_FORMAT} version {version!r}")
        sections = set(_ENVELOPE)
        if version >= TYPES_VERSION:
            sections |= _TYPE_SECTIONS
        if version >= BUNDLE_VERSION:
            sections |= _CONTENT_SECTIONS
        unknown = data.keys() - sections
        if unknown:
            raise InvalidBundleError(f"the file has unknown keys {sorted(unknown)}")
        bundle = Bundle(
            id=BUNDLE_FORMAT,
            presets=tuple(
                _preset(raw, n) for n, raw in enumerate(_section(data, "presets"))
            ),
            relationship_types=tuple(
                _relationship_type(raw, n)
                for n, raw in enumerate(_section(data, "relationship_types"))
            ),
            item_types=tuple(
                _item_type(raw, n) for n, raw in enumerate(_section(data, "item_types"))
            ),
            items=tuple(_item(raw, n) for n, raw in enumerate(_section(data, "items"))),
            connections=tuple(
                _connection(raw, n)
                for n, raw in enumerate(_section(data, "connections"))
            ),
            collections=tuple(
                _collection(raw, n)
                for n, raw in enumerate(_section(data, "collections"))
            ),
        )
        _check_links(bundle)
        return bundle

    def encode(self, bundle: Bundle) -> dict[str, Any]:
        """Write `bundle` as a version 3 file."""
        return {
            "format": BUNDLE_FORMAT,
            "version": BUNDLE_VERSION,
            "presets": [
                {
                    "ref": p.ref,
                    "kind": p.kind,
                    "label": p.label,
                    "description": p.description,
                    "definition": p.definition,
                }
                for p in bundle.presets
            ],
            "relationship_types": [
                {
                    "ref": r.ref,
                    "slug": r.slug,
                    "label": r.label,
                    "reverse_label": r.reverse_label,
                    "description": r.description,
                    "directional": r.directional,
                    "attributes_schema": r.attributes_schema,
                }
                for r in bundle.relationship_types
            ],
            "item_types": [
                {
                    "ref": t.ref,
                    "slug": t.slug,
                    "label": t.label,
                    "description": t.description,
                    "attributes_schema": t.attributes_schema,
                    "icon": t.icon,
                    "colour": t.colour,
                }
                for t in bundle.item_types
            ],
            "items": [
                {
                    "ref": i.ref,
                    "type_ref": i.type_ref,
                    "name": i.name,
                    "description": i.description,
                    "attributes": i.attributes,
                    "tags": list(i.tags),
                    "extra_schema": i.extra_schema,
                }
                for i in bundle.items
            ],
            "connections": [
                {
                    "source_ref": c.source_ref,
                    "target_ref": c.target_ref,
                    "type_ref": c.type_ref,
                    "attributes": c.attributes,
                }
                for c in bundle.connections
            ],
            "collections": [
                {
                    "ref": c.ref,
                    "name": c.name,
                    "description": c.description,
                    "item_refs": list(c.item_refs),
                    "definition": c.definition,
                }
                for c in bundle.collections
            ],
        }
