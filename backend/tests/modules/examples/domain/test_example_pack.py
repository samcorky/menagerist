"""Tests for the example pack value objects and their validation."""

from typing import Any

import pytest

from app.modules.examples.domain.errors import InvalidPackError
from app.modules.examples.domain.pack import (
    MAX_CONNECTIONS,
    MAX_ITEMS,
    MAX_PRESETS,
    MAX_TYPES,
    ExamplePack,
    PackConnection,
    PackItem,
    PackItemType,
    PackPreset,
    PackRelationshipType,
    preset_refs,
    resolve_preset_refs,
)

_LIST = {"$preset": "grades"}
_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "condition": {
            "type": "string",
            "x-menagerist": {"kind": "choice", "list": _LIST},
        }
    },
}


def _pack(**overrides: object) -> ExamplePack:
    base: dict[str, object] = {
        "id": "demo",
        "presets": (
            PackPreset(
                ref="grades",
                kind="choice_list",
                label="Grades",
                definition={"options": ["Mint"]},
            ),
        ),
        "relationship_types": (
            PackRelationshipType(ref="signed-by", slug="signed-by", label="Signed by"),
        ),
        "item_types": (
            PackItemType(
                ref="record",
                slug="record",
                label="Record",
                attributes_schema=_SCHEMA,
            ),
            PackItemType(ref="person", slug="person", label="Person"),
        ),
        "items": (
            PackItem(ref="a", type_ref="record", name="A"),
            PackItem(ref="b", type_ref="person", name="B"),
        ),
        "connections": (
            PackConnection(source_ref="a", target_ref="b", type_ref="signed-by"),
        ),
    }
    base.update(overrides)
    return ExamplePack(**base)  # type: ignore[arg-type]


def test_a_valid_pack_reports_its_counts() -> None:
    """A valid pack counts each of its sections."""
    counts = _pack().counts
    assert (counts.presets, counts.relationship_types, counts.item_types) == (1, 1, 2)
    assert (counts.items, counts.connections) == (2, 1)


@pytest.mark.parametrize(
    "overrides",
    [
        {"id": "Bad Id"},
        {
            "items": (
                PackItem(ref="a", type_ref="record", name="A"),
                PackItem(ref="a", type_ref="person", name="Dup"),
            )
        },
        {"items": (PackItem(ref="a", type_ref="nope", name="A"),)},
        {
            "connections": (
                PackConnection(source_ref="a", target_ref="zz", type_ref="signed-by"),
            )
        },
        {
            "connections": (
                PackConnection(source_ref="a", target_ref="b", type_ref="nope"),
            )
        },
        {
            "connections": (
                PackConnection(source_ref="a", target_ref="a", type_ref="signed-by"),
            )
        },
        {
            "item_types": (
                PackItemType(ref="record", slug="Record Type", label="Record"),
            )
        },
        {
            "item_types": (
                PackItemType(ref="record", slug="record", label="R"),
                PackItemType(ref="person", slug="record", label="P"),
            )
        },
        {
            "presets": (PackPreset(ref="Bad Ref", kind="choice_list", label="Grades"),),
            "item_types": (PackItemType(ref="person", slug="person", label="P"),),
            "items": (),
            "connections": (),
        },
        {"presets": ()},  # the schema still references the "grades" preset
    ],
)
def test_an_invalid_pack_is_rejected(overrides: dict[str, object]) -> None:
    """Each broken reference, slug or id is rejected on construction."""
    with pytest.raises(InvalidPackError):
        _pack(**overrides)


def _sized(field: str, count: int) -> dict[str, object]:
    """Overrides that make `field` hold `count` entries, all otherwise valid."""
    if field == "presets":
        return {
            "presets": tuple(
                PackPreset(
                    ref=f"p{n}",
                    kind="choice_list",
                    label=f"P{n}",
                    definition={"options": ["x"]},
                )
                for n in range(count)
            ),
            "item_types": (PackItemType(ref="person", slug="person", label="P"),),
            "items": (PackItem(ref="a", type_ref="person", name="A"),),
            "connections": (),
        }
    if field == "relationship_types":
        return {
            "relationship_types": tuple(
                PackRelationshipType(ref=f"r{n}", slug=f"r{n}", label="R")
                for n in range(count)
            ),
            "connections": (),
        }
    if field == "item_types":
        return {
            "item_types": tuple(
                PackItemType(ref=f"t{n}", slug=f"t{n}", label="T") for n in range(count)
            ),
            "items": tuple(
                PackItem(ref=f"i{n}", type_ref="t0", name="I") for n in range(2)
            ),
            "connections": (),
        }
    if field == "items":
        return {
            "items": tuple(
                PackItem(ref=f"i{n}", type_ref="person", name=str(n))
                for n in range(count)
            ),
            "connections": (),
        }
    return {
        "connections": tuple(
            PackConnection(source_ref="a", target_ref="b", type_ref="signed-by")
            for _ in range(count)
        )
    }


@pytest.mark.parametrize(
    ("field", "limit"),
    [
        ("presets", MAX_PRESETS),
        ("relationship_types", MAX_TYPES),
        ("item_types", MAX_TYPES),
        ("items", MAX_ITEMS),
        ("connections", MAX_CONNECTIONS),
    ],
)
def test_each_limit_accepts_exactly_the_maximum_and_rejects_one_over(
    field: str, limit: int
) -> None:
    """A pack at a limit is valid; one entry over it is rejected."""
    assert _pack(**_sized(field, limit)) is not None
    with pytest.raises(InvalidPackError, match="at most"):
        _pack(**_sized(field, limit + 1))


def test_preset_refs_finds_markers_anywhere() -> None:
    """Markers are found in nested dicts and lists; None has none."""
    assert preset_refs(_SCHEMA) == {"grades"}
    assert preset_refs(None) == set()
    assert preset_refs({"a": [{"b": {"$preset": "x"}}]}) == {"x"}


def test_resolve_preset_refs_swaps_markers_for_ids() -> None:
    """Markers become ids in a copy; the input is untouched."""
    resolved = resolve_preset_refs(_SCHEMA, {"grades": "abc"})
    assert resolved["properties"]["condition"]["x-menagerist"]["list"] == "abc"
    assert _SCHEMA["properties"]["condition"]["x-menagerist"]["list"] == _LIST


def test_resolve_preset_refs_rejects_an_unknown_marker() -> None:
    """A marker with no matching id is rejected."""
    with pytest.raises(InvalidPackError):
        resolve_preset_refs(_SCHEMA, {})


def test_resolve_preset_refs_resolves_markers_inside_lists() -> None:
    """Markers within lists are replaced and other values pass through."""
    resolved = resolve_preset_refs([{"$preset": "grades"}, 1], {"grades": "abc"})
    assert resolved == ["abc", 1]
