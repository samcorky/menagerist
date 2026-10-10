import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.modules.examples.domain.errors import InvalidPackError
from app.modules.examples.domain.pack import (
    ExamplePack,
    PackCollection,
    PackConnection,
    PackCover,
    PackItem,
    PackItemType,
    PackPreset,
    PackRelationshipType,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

INDEX_FORMAT = "menagerist-examples-index"
PACK_FORMAT = "menagerist-example-pack"
FORMAT_VERSION = 1
# v2 adds the optional `collections` section; v3 adds an item type's `cover`;
# v4 adds `requires` and `pack:ref` references.
PACK_VERSIONS = (1, 2, 3, 4)

# Same rule as the domain's pack id; ids become file names, so keep it strict.
PACK_ID = re.compile(r"^[a-z0-9][a-z0-9-]*\Z")

_INDEX = "the examples index"
_PACK = "the pack"
_SECTIONS = {"presets", "relationship_types", "item_types", "items", "connections"}
_V2_SECTIONS = {"collections"}
_V4_KEYS = {"requires"}


@dataclass(kw_only=True, frozen=True)
class IndexEntry:
    """One line of the catalogue index."""

    id: str
    name: str
    description: str


def _object(value: object, where: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise InvalidPackError(f"{where} must be an object")
    return value


def _array(value: object, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise InvalidPackError(f"{where} must be an array")
    return value


def _check_keys(
    data: Mapping[str, Any],
    *,
    required: set[str],
    optional: set[str],
    where: str,
) -> None:
    missing = required - set(data)
    if missing:
        raise InvalidPackError(f"{where} is missing {sorted(missing)[0]!r}")
    unknown = set(data) - required - optional
    if unknown:
        raise InvalidPackError(f"{where} has unknown key {sorted(unknown)[0]!r}")


def _str(value: object, where: str) -> str:
    if not isinstance(value, str):
        raise InvalidPackError(f"{where} must be a string")
    return value


def _opt_str(value: object, where: str) -> str | None:
    return None if value is None else _str(value, where)


def _bool(value: object, where: str) -> bool:
    if not isinstance(value, bool):
        raise InvalidPackError(f"{where} must be a boolean")
    return value


def _dict(value: object, where: str) -> dict[str, Any]:
    return dict(_object(value, where))


def _opt_object(value: object, where: str) -> dict[str, Any] | None:
    return None if value is None else _dict(value, where)


def _envelope(
    data: object,
    expected: str,
    where: str,
    versions: tuple[int, ...] = (FORMAT_VERSION,),
) -> Mapping[str, Any]:
    root = _object(data, where)
    if root.get("format") != expected:
        raise InvalidPackError(f"{where} format must be '{expected}'")
    version = root.get("version")
    if type(version) is not int or version not in versions:
        raise InvalidPackError(
            f"{where} version {root.get('version')!r} is not supported"
        )
    return root


def parse_index(data: object) -> list[IndexEntry]:
    """Parse `index.json`.

    Raises:
        InvalidPackError: If the index is malformed.
    """
    root = _envelope(data, INDEX_FORMAT, _INDEX)
    _check_keys(
        root, required={"format", "version", "packs"}, optional=set(), where=_INDEX
    )
    entries: list[IndexEntry] = []
    seen: set[str] = set()
    for n, raw in enumerate(_array(root["packs"], "packs")):
        where = f"packs[{n}]"
        entry = _object(raw, where)
        _check_keys(
            entry,
            required={"id", "name", "description"},
            optional=set(),
            where=where,
        )
        pack_id = _str(entry["id"], "id")
        if not PACK_ID.match(pack_id):
            raise InvalidPackError(f"{where} id is not a valid pack id")
        if pack_id in seen:
            raise InvalidPackError(f"{where} id '{pack_id}' is listed twice")
        seen.add(pack_id)
        entries.append(
            IndexEntry(
                id=pack_id,
                name=_str(entry["name"], "name"),
                description=_str(entry["description"], "description"),
            )
        )
    return entries


def _section(root: Mapping[str, Any], name: str) -> list[Mapping[str, Any]]:
    raw = _array(root.get(name, []), name)
    return [_object(v, f"{name}[{n}]") for n, v in enumerate(raw)]


def _parse_preset(p: Mapping[str, Any]) -> PackPreset:
    _check_keys(
        p,
        required={"ref", "kind", "label", "definition"},
        optional={"description"},
        where="a preset",
    )
    return PackPreset(
        ref=_str(p["ref"], "ref"),
        kind=_str(p["kind"], "kind"),
        label=_str(p["label"], "label"),
        description=_opt_str(p.get("description"), "description"),
        definition=_dict(p["definition"], "definition"),
    )


def _parse_relationship_type(t: Mapping[str, Any]) -> PackRelationshipType:
    _check_keys(
        t,
        required={"ref", "slug", "label"},
        optional={"reverse_label", "description", "directional", "attributes_schema"},
        where="a relationship type",
    )
    return PackRelationshipType(
        ref=_str(t["ref"], "ref"),
        slug=_str(t["slug"], "slug"),
        label=_str(t["label"], "label"),
        reverse_label=_opt_str(t.get("reverse_label"), "reverse_label"),
        description=_opt_str(t.get("description"), "description"),
        directional=_bool(t.get("directional", True), "directional"),
        attributes_schema=_opt_object(t.get("attributes_schema"), "attributes_schema"),
    )


def _parse_cover(c: object) -> PackCover:
    cover = _object(c, "cover")
    _check_keys(cover, required={"style"}, optional=set(), where="a cover")
    return PackCover(style=_str(cover["style"], "style"))


def _parse_item_type(t: Mapping[str, Any]) -> PackItemType:
    _check_keys(
        t,
        required={"ref", "slug", "label"},
        optional={"description", "attributes_schema", "cover"},
        where="an item type",
    )
    return PackItemType(
        ref=_str(t["ref"], "ref"),
        slug=_str(t["slug"], "slug"),
        label=_str(t["label"], "label"),
        description=_opt_str(t.get("description"), "description"),
        attributes_schema=_opt_object(t.get("attributes_schema"), "attributes_schema"),
        cover=None if t.get("cover") is None else _parse_cover(t["cover"]),
    )


def _parse_item(i: Mapping[str, Any]) -> PackItem:
    _check_keys(
        i,
        required={"ref", "type", "name"},
        optional={"description", "attributes", "tags", "extra_schema"},
        where="an item",
    )
    return PackItem(
        ref=_str(i["ref"], "ref"),
        type_ref=_str(i["type"], "type"),
        name=_str(i["name"], "name"),
        description=_opt_str(i.get("description"), "description"),
        attributes=_dict(i.get("attributes", {}), "attributes"),
        tags=tuple(_str(t, "tag") for t in _array(i.get("tags", []), "tags")),
        extra_schema=_opt_object(i.get("extra_schema"), "extra_schema"),
    )


def _parse_connection(c: Mapping[str, Any]) -> PackConnection:
    _check_keys(
        c,
        required={"from", "to", "type"},
        optional={"attributes"},
        where="a connection",
    )
    return PackConnection(
        source_ref=_str(c["from"], "from"),
        target_ref=_str(c["to"], "to"),
        type_ref=_str(c["type"], "type"),
        attributes=_dict(c.get("attributes", {}), "attributes"),
    )


def _parse_collection(c: Mapping[str, Any]) -> PackCollection:
    _check_keys(
        c,
        required={"ref", "name", "items"},
        optional={"description"},
        where="a collection",
    )
    return PackCollection(
        ref=_str(c["ref"], "ref"),
        name=_str(c["name"], "name"),
        description=_opt_str(c.get("description"), "description"),
        item_refs=tuple(_str(r, "item") for r in _array(c["items"], "items")),
    )


def _parse_all[T](
    root: Mapping[str, Any], name: str, parse: Callable[[Mapping[str, Any]], T]
) -> tuple[T, ...]:
    return tuple(parse(raw) for raw in _section(root, name))


def parse_pack(data: object) -> ExamplePack:
    """Parse one pack file; unknown keys and wrong types are rejected.

    Raises:
        InvalidPackError: If the file is malformed or the pack is inconsistent.
    """
    root = _envelope(data, PACK_FORMAT, _PACK, PACK_VERSIONS)
    optional = (
        _SECTIONS
        | (_V2_SECTIONS if root["version"] >= 2 else set())
        | (_V4_KEYS if root["version"] >= 4 else set())
    )
    _check_keys(
        root, required={"format", "version", "id"}, optional=optional, where=_PACK
    )
    return ExamplePack(
        id=_str(root["id"], "id"),
        presets=_parse_all(root, "presets", _parse_preset),
        relationship_types=_parse_all(
            root, "relationship_types", _parse_relationship_type
        ),
        item_types=_parse_all(root, "item_types", _parse_item_type),
        items=_parse_all(root, "items", _parse_item),
        connections=_parse_all(root, "connections", _parse_connection),
        collections=_parse_all(root, "collections", _parse_collection),
        requires=tuple(
            _str(r, "requires entry")
            for r in _array(root.get("requires", []), "requires")
        ),
    )
