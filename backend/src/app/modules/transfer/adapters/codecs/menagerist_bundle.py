"""The `menagerist-bundle` file: Menagerist's own export and import format."""

from collections.abc import Mapping
from typing import Any

from app.modules.transfer.domain.bundle import (
    BUNDLE_FORMAT,
    BUNDLE_VERSION,
    PRESETS_ONLY_VERSION,
    REF_PATTERN,
    REF_RULE,
    Bundle,
    BundleItemType,
    BundlePreset,
    BundleRelationshipType,
)
from app.modules.transfer.domain.errors import InvalidBundleError

_ENVELOPE = {"format", "version", "presets"}
_TYPE_SECTIONS = {"relationship_types", "item_types"}
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
        if version not in (PRESETS_ONLY_VERSION, BUNDLE_VERSION):
            raise InvalidBundleError(f"unsupported {BUNDLE_FORMAT} version {version!r}")
        sections = _ENVELOPE | (_TYPE_SECTIONS if version == BUNDLE_VERSION else set())
        unknown = data.keys() - sections
        if unknown:
            raise InvalidBundleError(f"the file has unknown keys {sorted(unknown)}")
        return Bundle(
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
        )

    def encode(self, bundle: Bundle) -> dict[str, Any]:
        """Write `bundle` as a version 2 file."""
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
        }
