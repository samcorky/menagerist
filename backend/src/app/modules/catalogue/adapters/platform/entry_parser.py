import json
import re
from typing import Any

from app.modules.catalogue.domain.entry import CatalogueEntry, EntrySection
from app.modules.catalogue.domain.errors import InvalidEntryError
from app.modules.transfer.domain.bundle import (
    PackItemType,
    PackPreset,
    PackRelationshipType,
)
from app.platform.shared_data import shared_data_path

ENTRY_ID = re.compile(r"^[a-z0-9][a-z0-9-]*\Z")
_ISO_DATA = "data/iso-data.json"


def _object(value: object, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InvalidEntryError(f"{where} must be an object")
    return value


def _text(data: dict[str, Any], key: str, where: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise InvalidEntryError(f"{where} needs a non-blank '{key}'")
    return value


def _countries() -> list[PackPreset]:
    with shared_data_path(_ISO_DATA).open(encoding="utf-8") as f:
        names = [c["name"] for c in json.load(f)["countries"]]
    return [
        PackPreset(
            ref="preset-1",
            kind="choice_list",
            label="Countries",
            definition={"options": names},
        )
    ]


def _presets(value: object, where: str) -> tuple[PackPreset, ...]:
    block = _object(value, f"{where} presets")
    if block.get("generated") == "iso-countries":
        return tuple(_countries())
    if "generated" in block:
        raise InvalidEntryError(f"{where} names an unknown generated list")
    items = block.get("items")
    if not isinstance(items, list):
        raise InvalidEntryError(f"{where} presets need an 'items' array")
    return tuple(
        PackPreset(
            ref=f"preset-{n}",
            kind=_text(item := _object(raw, where), "kind", where),
            label=_text(item, "label", where),
            description=item.get("description"),
            definition=_object(item.get("definition"), f"{where} definition"),
        )
        for n, raw in enumerate(items, start=1)
    )


def _item_types(value: object, where: str) -> tuple[PackItemType, ...]:
    if not isinstance(value, list):
        raise InvalidEntryError(f"{where} itemTypes must be an array")
    result = []
    for raw in value:
        item = _object(raw, where)
        slug = _text(item, "slug", where)
        result.append(
            PackItemType(
                ref=slug,
                slug=slug,
                label=_text(item, "label", where),
                description=item.get("description"),
            )
        )
    return tuple(result)


def _relationship_types(value: object, where: str) -> tuple[PackRelationshipType, ...]:
    if not isinstance(value, list):
        raise InvalidEntryError(f"{where} relationshipTypes must be an array")
    result = []
    for raw in value:
        item = _object(raw, where)
        slug = _text(item, "slug", where)
        result.append(
            PackRelationshipType(
                ref=slug,
                slug=slug,
                label=_text(item, "label", where),
                reverse_label=item.get("reverseLabel"),
                description=item.get("description"),
                directional=bool(item.get("directional", True)),
            )
        )
    return tuple(result)


def parse_entry(data: object) -> CatalogueEntry:
    """Build an entry from its JSON, or raise `InvalidEntryError`."""
    entry = _object(data, "an entry")
    entry_id = _text(entry, "id", "an entry")
    if not ENTRY_ID.match(entry_id):
        raise InvalidEntryError(f"entry id '{entry_id}' must be lowercase and hyphens")
    where = f"entry '{entry_id}'"
    try:
        section = EntrySection(str(entry.get("section")))
    except ValueError:
        raise InvalidEntryError(f"{where} has an unknown section") from None
    return CatalogueEntry(
        id=entry_id,
        title=_text(entry, "title", where),
        description=_text(entry, "description", where),
        section=section,
        presets=_presets(entry["presets"], where) if "presets" in entry else (),
        item_types=_item_types(entry.get("itemTypes", []), where),
        relationship_types=_relationship_types(
            entry.get("relationshipTypes", []), where
        ),
    )
