import copy
from dataclasses import asdict
from typing import Any

import pytest

from app.modules.examples.adapters.platform.pack_parser import parse_index, parse_pack
from app.modules.examples.domain.errors import InvalidPackError
from app.modules.examples.domain.pack import PackCover

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
    (["version"], 4),
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


def _v2_with_collections(pack_data: dict[str, Any]) -> dict[str, Any]:
    return {
        **pack_data,
        "version": 2,
        "collections": [
            {
                "ref": "starters",
                "name": "Starters",
                "description": "Where to begin",
                "items": ["a", "b"],
            },
            {"ref": "just-a", "name": "Just A", "items": ["a"]},
        ],
    }


def test_parses_a_v2_pack_with_collections(pack_data: dict[str, Any]) -> None:
    """A version 2 pack carries its collections and counts them."""
    pack = parse_pack(_v2_with_collections(pack_data))

    assert pack.counts.collections == 2
    assert pack.collections[0].ref == "starters"
    assert pack.collections[0].description == "Where to begin"
    assert pack.collections[0].item_refs == ("a", "b")
    assert pack.collections[1].description is None


def test_a_v1_pack_has_no_collections(pack_data: dict[str, Any]) -> None:
    """A version 1 pack still parses, with an empty collections section."""
    pack = parse_pack(pack_data)

    assert pack.collections == ()
    assert pack.counts.collections == 0


def test_a_v2_pack_may_omit_collections(pack_data: dict[str, Any]) -> None:
    """Version 2 allows the section but does not require it."""
    pack = parse_pack({**pack_data, "version": 2})

    assert pack.collections == ()


def test_collections_on_a_v1_pack_are_rejected(pack_data: dict[str, Any]) -> None:
    """The `collections` section needs version 2."""
    data = {**_v2_with_collections(pack_data), "version": 1}

    with pytest.raises(InvalidPackError, match="collections"):
        parse_pack(data)


_BAD_COLLECTION: list[tuple[list[str | int], object]] = [
    (["collections", 0, "colour"], "red"),
    (["collections", 0, "ref"], 5),
    (["collections", 0, "ref"], "Bad Ref"),
    (["collections", 0, "name"], 5),
    (["collections", 0, "name"], "   "),
    (["collections", 0, "description"], 3),
    (["collections", 0, "items"], "a"),
    (["collections", 0, "items"], [1]),
    (["collections", 0, "items"], []),
    (["collections", 0, "items"], ["a", "a"]),
    (["collections", 0, "items"], ["a", "zz"]),
    (["collections", 1, "ref"], "starters"),
    (["collections", 0], "nope"),
    (["collections"], "nope"),
]


@pytest.mark.parametrize(("path", "value"), _BAD_COLLECTION)
def test_a_malformed_collection_is_an_invalid_pack_error(
    pack_data: dict[str, Any], path: list[str | int], value: object
) -> None:
    """Bad collection keys, types, names, members and refs are rejected."""
    with pytest.raises(InvalidPackError):
        parse_pack(_mutated(_v2_with_collections(pack_data), path, value))


@pytest.mark.parametrize("key", ["ref", "name", "items"])
def test_a_collection_missing_a_key_is_an_invalid_pack_error(
    pack_data: dict[str, Any], key: str
) -> None:
    """`ref`, `name` and `items` are required on a collection."""
    data = _v2_with_collections(pack_data)
    del data["collections"][0][key]

    with pytest.raises(InvalidPackError):
        parse_pack(data)


def test_a_v3_pack_parses_item_type_covers(pack_data: dict[str, Any]) -> None:
    """A version 3 item type may carry a cover style."""
    pack_data["version"] = 3
    pack_data["item_types"][0]["cover"] = {"style": "poster"}

    pack = parse_pack(pack_data)

    assert isinstance(pack.item_types[0].cover, PackCover)
    assert pack.item_types[0].cover.style == "poster"
    assert asdict(pack.counts) == {
        "presets": 1,
        "relationship_types": 1,
        "item_types": 1,
        "items": 2,
        "connections": 1,
        "collections": 0,
    }


def test_a_cover_is_optional(pack_data: dict[str, Any]) -> None:
    """Item types without a cover parse with `cover` unset, on every version."""
    for version in (1, 2, 3):
        pack = parse_pack({**pack_data, "version": version})
        assert pack.item_types[0].cover is None


@pytest.mark.parametrize("version", [1, 2])
def test_a_cover_is_accepted_on_older_versions(
    pack_data: dict[str, Any], version: int
) -> None:
    """The parser does not gate `cover` by version; it is documented as v3."""
    pack_data["version"] = version
    pack_data["item_types"][0]["cover"] = {"style": "box"}

    cover = parse_pack(pack_data).item_types[0].cover
    assert cover is not None
    assert cover.style == "box"


@pytest.mark.parametrize(
    "cover",
    [
        {"style": "hologram"},
        {"style": 3},
        {},
        {"style": "card", "colour": "red"},
        "poster",
        ["card"],
    ],
)
def test_a_malformed_cover_is_an_invalid_pack_error(
    pack_data: dict[str, Any], cover: object
) -> None:
    """Unknown styles, wrong types, missing or extra keys are rejected."""
    pack_data["version"] = 3
    pack_data["item_types"][0]["cover"] = cover

    with pytest.raises(InvalidPackError):
        parse_pack(pack_data)


def test_a_null_cover_means_no_cover(pack_data: dict[str, Any]) -> None:
    """An explicit `cover: null` parses as no cover."""
    pack_data["item_types"][0]["cover"] = None

    assert parse_pack(pack_data).item_types[0].cover is None


def test_a_v3_pack_may_carry_collections(pack_data: dict[str, Any]) -> None:
    """Version 3 keeps the `collections` section that version 2 introduced."""
    pack = parse_pack({**_v2_with_collections(pack_data), "version": 3})

    assert pack.counts.collections == 2


def test_an_unknown_cover_style_names_its_item_type(
    pack_data: dict[str, Any],
) -> None:
    """The error says which item type has the bad style."""
    pack_data["item_types"][0]["cover"] = {"style": "hologram"}

    with pytest.raises(InvalidPackError, match="'thing'"):
        parse_pack(pack_data)
