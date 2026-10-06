import copy
from typing import Any

import pytest

from app.modules.examples.adapters.platform.pack_parser import parse_index, parse_pack
from app.modules.examples.domain.errors import InvalidPackError

_INDEX: dict[str, Any] = {
    "format": "menagerist-examples-index",
    "version": 1,
    "packs": [{"id": "demo", "name": "Demo", "description": "A demo"}],
}


def test_parses_a_pack(pack_data: dict[str, Any]) -> None:
    """A valid pack parses into domain values."""
    pack = parse_pack(pack_data)

    assert pack.id == "demo"
    assert pack.counts.items == 2
    assert pack.items[0].tags == ("x",)
    assert pack.items[0].type_ref == "thing"
    assert pack.relationship_types[0].reverse_label == "Made"
    assert pack.relationship_types[0].directional is True
    assert pack.connections[0].source_ref == "a"
    assert pack.presets[0].definition == {"options": ["Mint"]}


def test_parses_optional_fields(pack_data: dict[str, Any]) -> None:
    """Optional fields are carried through when given."""
    pack_data["relationship_types"][0]["directional"] = False
    pack_data["item_types"][0]["attributes_schema"] = {"type": "object"}
    pack_data["items"][0]["attributes"] = {"k": 1}

    pack = parse_pack(pack_data)

    assert pack.relationship_types[0].directional is False
    assert pack.item_types[0].attributes_schema == {"type": "object"}
    assert pack.items[0].attributes == {"k": 1}


def _mutated(data: dict[str, Any], path: list[str | int], value: object) -> object:
    data = copy.deepcopy(data)
    target: Any = data
    for step in path[:-1]:
        target = target[step]
    target[path[-1]] = value
    return data


_BAD: list[tuple[list[str | int], object]] = [
    (["format"], "other"),
    (["version"], 2),
    (["surprise"], 1),
    (["items"], "nope"),
    (["items", 0], "nope"),
    (["items", 0, "colour"], "red"),
    (["items", 0, "type"], 5),
    (["items", 0, "tags"], "x"),
    (["items", 0, "tags"], [1]),
    (["items", 0, "attributes"], []),
    (["items", 0, "extra_schema"], "x"),
    (["items", 0, "description"], 3),
    (["relationship_types", 0, "directional"], "yes"),
    (["relationship_types", 0, "directional"], 1),
    (["relationship_types", 0, "attributes_schema"], []),
    (["item_types", 0, "attributes_schema"], "x"),
    (["presets", 0, "definition"], []),
    (["connections", 0, "attributes"], "x"),
    (["connections", 0, "extra"], 1),
]


@pytest.mark.parametrize(("path", "value"), _BAD)
def test_a_malformed_pack_is_an_invalid_pack_error(
    pack_data: dict[str, Any], path: list[str | int], value: object
) -> None:
    """Bad values, unknown keys and wrong types raise `InvalidPackError`."""
    with pytest.raises(InvalidPackError):
        parse_pack(_mutated(pack_data, path, value))


@pytest.mark.parametrize(
    ("section", "key"),
    [
        (None, "id"),
        ("items", "name"),
        ("items", "type"),
        ("connections", "type"),
        ("presets", "definition"),
        ("relationship_types", "label"),
        ("item_types", "slug"),
    ],
)
def test_a_missing_key_is_an_invalid_pack_error(
    pack_data: dict[str, Any], section: str | None, key: str
) -> None:
    """A missing required key raises `InvalidPackError`."""
    target = pack_data if section is None else pack_data[section][0]
    del target[key]

    with pytest.raises(InvalidPackError):
        parse_pack(pack_data)


@pytest.mark.parametrize("data", [[], "x", None, 3])
def test_a_non_object_root_is_an_invalid_pack_error(data: object) -> None:
    """A root that is not an object raises `InvalidPackError`."""
    with pytest.raises(InvalidPackError):
        parse_pack(data)


def test_parses_an_index() -> None:
    """A valid index parses into entries."""
    entries = parse_index(_INDEX)

    assert [(e.id, e.name, e.description) for e in entries] == [
        ("demo", "Demo", "A demo")
    ]


@pytest.mark.parametrize(
    "data",
    [
        [],
        {**_INDEX, "format": "x"},
        {**_INDEX, "version": 2},
        {**_INDEX, "packs": [{"id": "demo"}]},
        {**_INDEX, "packs": "nope"},
        {**_INDEX, "packs": [{"id": 1, "name": "n", "description": "d"}]},
        {**_INDEX, "extra": 1},
        {k: v for k, v in _INDEX.items() if k != "packs"},
    ],
)
def test_a_malformed_index_is_an_invalid_pack_error(data: object) -> None:
    """A malformed index raises `InvalidPackError`."""
    with pytest.raises(InvalidPackError):
        parse_index(data)


@pytest.mark.parametrize("pack_id", ["../x", "a/b", "/abs", "A_B", ""])
def test_an_index_id_that_is_not_a_valid_pack_id_is_rejected(pack_id: str) -> None:
    """Index ids become file names, so unsafe ones are rejected."""
    packs = [{"id": pack_id, "name": "n", "description": "d"}]

    with pytest.raises(InvalidPackError):
        parse_index({**_INDEX, "packs": packs})


def test_a_duplicate_index_id_is_rejected() -> None:
    """The same id cannot be listed twice."""
    entry = {"id": "demo", "name": "n", "description": "d"}

    with pytest.raises(InvalidPackError):
        parse_index({**_INDEX, "packs": [entry, entry]})


@pytest.mark.parametrize("version", [True, 1.0])
def test_a_version_that_is_not_the_integer_one_is_rejected(
    pack_data: dict[str, Any], version: object
) -> None:
    """`true` and `1.0` equal 1 in Python but are not the integer version."""
    with pytest.raises(InvalidPackError):
        parse_index({**_INDEX, "version": version})
    with pytest.raises(InvalidPackError):
        parse_pack({**pack_data, "version": version})
