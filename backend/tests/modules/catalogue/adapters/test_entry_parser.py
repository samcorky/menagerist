import json
from typing import Any

import pytest

from app.modules.catalogue.adapters.platform.entry_parser import parse_entry
from app.modules.catalogue.domain.entry import EntrySection
from app.modules.catalogue.domain.errors import InvalidEntryError
from app.platform.shared_data import shared_data_path


def _preset_entry() -> dict[str, Any]:
    return {
        "id": "grades",
        "title": "Grades",
        "description": "d",
        "section": "choice_list",
        "presets": {
            "format": "menagerist-presets",
            "version": 1,
            "items": [
                {
                    "kind": "choice_list",
                    "label": "Grades",
                    "description": None,
                    "definition": {"options": ["A"]},
                }
            ],
        },
    }


def _types_entry() -> dict[str, Any]:
    return {
        "id": "starter",
        "title": "Starter",
        "description": "d",
        "section": "starter_types",
        "itemTypes": [{"slug": "person", "label": "Person", "description": None}],
        "relationshipTypes": [
            {
                "slug": "part-of",
                "label": "Part of",
                "reverseLabel": "Has part",
                "description": None,
                "directional": True,
            }
        ],
    }


def test_a_preset_entry_is_parsed_with_numbered_refs() -> None:
    """A preset entry is parsed with numbered refs."""
    entry = parse_entry(_preset_entry())
    assert entry.section is EntrySection.CHOICE_LIST
    assert [p.ref for p in entry.presets] == ["preset-1"]
    assert entry.presets[0].definition == {"options": ["A"]}


def test_a_starter_types_entry_is_parsed() -> None:
    """A starter types entry is parsed."""
    entry = parse_entry(_types_entry())
    assert entry.item_types[0].slug == "person"
    rel = entry.relationship_types[0]
    assert (rel.ref, rel.reverse_label, rel.directional) == (
        "part-of",
        "Has part",
        True,
    )


def test_countries_are_generated_from_the_iso_data() -> None:
    """Countries are generated from the iso data."""
    data = _preset_entry()
    data["presets"] = {"generated": "iso-countries"}
    entry = parse_entry(data)
    with shared_data_path("data/iso-data.json").open(encoding="utf-8") as f:
        names = [c["name"] for c in json.load(f)["countries"]]
    assert entry.presets[0].label == "Countries"
    assert entry.presets[0].definition == {"options": names}


@pytest.mark.parametrize(
    "change",
    [
        {"section": "nope"},
        {"id": None},
        {"id": "Bad Id"},
        {"title": ""},
        {"presets": {"generated": "unknown"}},
        {"presets": "text"},
    ],
)
def test_a_malformed_entry_is_rejected(change: dict[str, Any]) -> None:
    """A malformed entry is rejected."""
    data = {**_preset_entry(), **change}
    if data["id"] is None:
        del data["id"]
    with pytest.raises(InvalidEntryError):
        parse_entry(data)


def test_an_entry_that_is_not_an_object_is_rejected() -> None:
    """An entry that is not an object is rejected."""
    with pytest.raises(InvalidEntryError):
        parse_entry([])
