"""Tests for the example pack value objects and their validation."""

from typing import Any

import pytest

from app.modules.examples.domain.errors import InvalidPackError
from app.modules.examples.domain.installation import EntityKind
from app.modules.examples.domain.pack import (
    COVER_STYLES,
    MAX_CONNECTIONS,
    MAX_ITEMS,
    MAX_PRESETS,
    MAX_TYPES,
    ExamplePack,
    PackCollection,
    PackConnection,
    PackCover,
    PackItem,
    PackItemType,
    PackPreset,
    PackRelationshipType,
    preset_refs,
    resolve_preset_refs,
    split_ref,
    validate_catalogue,
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


def test_a_pack_counts_its_collections() -> None:
    """Collections are counted; a pack without them counts zero."""
    pack = _pack(
        collections=(PackCollection(ref="both", name="Both", item_refs=("a", "b")),)
    )

    assert pack.counts.collections == 1
    assert _pack().counts.collections == 0


def _collection(**overrides: object) -> PackCollection:
    base: dict[str, object] = {"ref": "both", "name": "Both", "item_refs": ("a", "b")}
    base.update(overrides)
    return PackCollection(**base)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "collections",
    [
        (_collection(ref="Bad Ref"),),
        (_collection(), _collection(name="Other")),
        (_collection(name="  "),),
        (_collection(item_refs=()),),
        (_collection(item_refs=("a", "a")),),
        (_collection(item_refs=("a", "zz")),),
    ],
)
def test_an_invalid_collection_is_rejected(
    collections: tuple[PackCollection, ...],
) -> None:
    """A bad ref, duplicate ref, blank name, or bad membership is rejected."""
    with pytest.raises(InvalidPackError):
        _pack(collections=collections)


def test_a_collection_name_may_be_120_characters_after_stripping() -> None:
    """Padding does not count towards the 120-character limit."""
    name = f"  {'n' * 120}  "

    pack = _pack(collections=(_collection(name=name),))

    assert len(pack.collections) == 1


def test_a_collection_name_over_120_characters_is_rejected() -> None:
    """The error names the collection's ref."""
    with pytest.raises(InvalidPackError, match=r"collection 'both'.*120"):
        _pack(collections=(_collection(name="n" * 121),))


def test_cover_styles_are_closed() -> None:
    """The cover styles are a fixed set, and each builds a cover."""
    assert COVER_STYLES == ("sleeve", "poster", "box", "card")
    assert all(PackCover(style=s).style == s for s in COVER_STYLES)


def test_an_unknown_cover_style_is_rejected() -> None:
    """An item type with a cover style outside the closed set cannot be built."""
    with pytest.raises(InvalidPackError, match=r"'record'.*cover style"):
        PackItemType(
            ref="record", slug="record", label="Record", cover=PackCover(style="x")
        )


def _addon(**overrides: object) -> ExamplePack:
    base: dict[str, object] = {
        "id": "addon",
        "requires": ("demo",),
        "item_types": (PackItemType(ref="extra", slug="extra", label="Extra"),),
        "items": (
            PackItem(ref="x", type_ref="demo:record", name="X"),
            PackItem(ref="y", type_ref="extra", name="Y"),
        ),
        "connections": (
            PackConnection(
                source_ref="x", target_ref="demo:b", type_ref="demo:signed-by"
            ),
        ),
        "collections": (
            PackCollection(ref="mix", name="Mix", item_refs=("x", "demo:a")),
        ),
    }
    base.update(overrides)
    return ExamplePack(**base)  # type: ignore[arg-type]


def test_split_ref_separates_an_optional_pack_prefix() -> None:
    """A local ref has no pack; a prefixed ref splits on its one colon."""
    assert split_ref("thing") == (None, "thing")
    assert split_ref("demo:thing") == ("demo", "thing")


@pytest.mark.parametrize(
    "ref", ["a:b:c", ":b", "a:", "A:b", "a:B_", ":", "demo:thing\n"]
)
def test_split_ref_rejects_a_malformed_prefixed_ref(ref: str) -> None:
    """Exactly one colon with a valid ref on each side."""
    with pytest.raises(InvalidPackError, match=r"exactly one colon|must be"):
        split_ref(ref)


def test_an_addon_pack_exposes_requires_and_external_refs() -> None:
    """External refs carry their kind, pack id and local ref."""
    pack = _addon()
    assert pack.requires == ("demo",)
    assert pack.external_refs() == frozenset(
        {
            (EntityKind.ITEM_TYPE, "demo", "record"),
            (EntityKind.ITEM, "demo", "b"),
            (EntityKind.RELATIONSHIP_TYPE, "demo", "signed-by"),
            (EntityKind.ITEM, "demo", "a"),
        }
    )


def test_a_pack_without_prefixed_refs_has_no_external_refs() -> None:
    """Ordinary packs have none and need nothing."""
    pack = _pack()
    assert pack.requires == ()
    assert pack.external_refs() == frozenset()


@pytest.mark.parametrize(
    "overrides",
    [
        {"requires": ("demo", "demo")},
        {"requires": ("addon",)},
        {"requires": ("Bad Id",)},
        {
            "requires": ("demo",),
            "items": (PackItem(ref="x", type_ref="other:t", name="X"),),
        },
    ],
)
def test_invalid_requires_or_unrequired_prefix_is_rejected(
    overrides: dict[str, object],
) -> None:
    """Requires must be unique, valid and not self; prefixes must be required."""
    with pytest.raises(InvalidPackError):
        _addon(**overrides)


def test_requires_errors_name_the_offending_value() -> None:
    """The messages name the pack id or ref."""
    with pytest.raises(InvalidPackError, match="'addon'"):
        _addon(requires=("addon",))
    with pytest.raises(InvalidPackError, match="'demo'"):
        _addon(requires=("demo", "demo"))
    with pytest.raises(InvalidPackError, match="'other:t'"):
        _addon(items=(PackItem(ref="x", type_ref="other:t", name="X"),))
    with pytest.raises(InvalidPackError, match="'other:b'"):
        _addon(
            connections=(
                PackConnection(source_ref="x", target_ref="other:b", type_ref="demo:t"),
            )
        )
    with pytest.raises(InvalidPackError, match="'other:a'"):
        _addon(collections=(PackCollection(ref="m", name="M", item_refs=("other:a",)),))


def test_an_empty_requires_is_allowed() -> None:
    """An empty list means the pack is not an add-on."""
    assert _pack(requires=()).requires == ()


def test_unprefixed_refs_still_resolve_only_locally() -> None:
    """A local ref naming a required pack's entity is unknown."""
    with pytest.raises(InvalidPackError, match="unknown"):
        _addon(items=(PackItem(ref="x", type_ref="record", name="X"),))
    with pytest.raises(InvalidPackError):
        _addon(
            collections=(PackCollection(ref="m", name="M", item_refs=("a",)),),
        )
    with pytest.raises(InvalidPackError):
        _addon(
            connections=(
                PackConnection(source_ref="x", target_ref="y", type_ref="signed-by"),
            )
        )


def test_a_connection_cannot_join_an_external_item_to_itself() -> None:
    """The self-join rule holds for prefixed ends."""
    with pytest.raises(InvalidPackError, match="itself"):
        _addon(
            connections=(
                PackConnection(
                    source_ref="demo:a", target_ref="demo:a", type_ref="demo:signed-by"
                ),
            )
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"items": (PackItem(ref="demo:x", type_ref="extra", name="X"),)},
        {"item_types": (PackItemType(ref="demo:t", slug="t", label="T"),)},
        {
            "relationship_types": (
                PackRelationshipType(ref="demo:r", slug="r", label="R"),
            )
        },
        {"presets": (PackPreset(ref="demo:p", kind="choice_list", label="P"),)},
        {"collections": (PackCollection(ref="demo:c", name="C", item_refs=("x",)),)},
        {"item_types": (PackItemType(ref="extra", slug="demo:extra", label="T"),)},
    ],
)
def test_a_prefixed_ref_in_a_definition_is_rejected(
    overrides: dict[str, object],
) -> None:
    """A pack's own definitions never carry a prefix."""
    with pytest.raises(InvalidPackError):
        _addon(**overrides)


def test_a_preset_marker_with_a_prefix_is_rejected() -> None:
    """Preset markers are local only."""
    schema = {"x": {"$preset": "demo:grades"}}
    with pytest.raises(InvalidPackError, match="demo:grades"):
        _addon(
            item_types=(
                PackItemType(
                    ref="extra", slug="extra", label="E", attributes_schema=schema
                ),
            )
        )


def _plain(pack_id: str, **overrides: object) -> ExamplePack:
    base: dict[str, object] = {
        "id": pack_id,
        "item_types": (PackItemType(ref="thing", slug="thing", label="Thing"),),
        "items": (PackItem(ref="a", type_ref="thing", name="A"),),
    }
    base.update(overrides)
    return ExamplePack(**base)  # type: ignore[arg-type]


def _chain(pack_id: str, *requires: str) -> ExamplePack:
    return _plain(pack_id, requires=requires)


def test_validate_catalogue_accepts_a_chain_of_addons() -> None:
    """An add-on may require another add-on; a pack with no refs is fine too."""
    validate_catalogue({})
    validate_catalogue(
        {
            "demo": _plain(
                "demo",
                relationship_types=(
                    PackRelationshipType(
                        ref="by", slug="by", label="By", reverse_label="Made"
                    ),
                ),
            ),
            "mid": _chain("mid", "demo"),
            "top": _plain(
                "top",
                requires=("mid", "demo"),
                items=(PackItem(ref="n", type_ref="demo:thing", name="N"),),
            ),
        }
    )


def test_validate_catalogue_rejects_an_unknown_required_pack() -> None:
    """A required pack that is not in the catalogue is named."""
    with pytest.raises(InvalidPackError, match="pack a requires ghost"):
        validate_catalogue({"a": _chain("a", "ghost")})


@pytest.mark.parametrize(
    ("packs", "message"),
    [
        (("a", "b"), "pack dependency cycle: a -> b -> a"),
        (("a", "b", "c"), "pack dependency cycle: a -> b -> c -> a"),
    ],
)
def test_validate_catalogue_rejects_a_cycle(
    packs: tuple[str, ...], message: str
) -> None:
    """A dependency cycle fails and names the packs in it."""
    catalogue = {
        pack_id: _chain(pack_id, packs[(i + 1) % len(packs)])
        for i, pack_id in enumerate(packs)
    }
    with pytest.raises(InvalidPackError, match=message):
        validate_catalogue(catalogue)


def test_validate_catalogue_names_only_the_cycle_not_the_way_in() -> None:
    """A pack leading into a cycle is not part of the reported cycle."""
    catalogue = {
        "entry": _chain("entry", "a"),
        "a": _chain("a", "b"),
        "b": _chain("b", "a"),
    }
    with pytest.raises(InvalidPackError, match=r"cycle: a -> b -> a$"):
        validate_catalogue(catalogue)


def test_validate_catalogue_accepts_a_diamond() -> None:
    """Two routes to the same base pack are not a cycle."""
    validate_catalogue(
        {
            "base": _plain("base"),
            "l": _chain("l", "base"),
            "r": _chain("r", "base"),
            "top": _chain("top", "l", "r"),
        }
    )


def test_validate_catalogue_rejects_a_dangling_ref() -> None:
    """A reference to something the named pack lacks names add-on, ref and pack."""
    addon = _plain(
        "extras",
        requires=("demo",),
        items=(PackItem(ref="x", type_ref="demo:nope", name="X"),),
    )
    message = "pack extras refers to demo:nope, which demo does not define as an item"
    with pytest.raises(InvalidPackError, match=message + " type"):
        validate_catalogue({"demo": _plain("demo"), "extras": addon})


def test_validate_catalogue_rejects_a_ref_of_the_wrong_kind() -> None:
    """An item named where an item type is expected is refused."""
    addon = _plain(
        "extras",
        requires=("demo",),
        items=(PackItem(ref="x", type_ref="demo:a", name="X"),),
    )
    with pytest.raises(InvalidPackError, match="demo:a, which demo does not define"):
        validate_catalogue({"demo": _plain("demo"), "extras": addon})


def test_validate_catalogue_checks_item_and_relationship_refs() -> None:
    """Connection and collection refs are checked against items and types."""
    base = _plain("demo")
    bad_item = _plain(
        "e1",
        requires=("demo",),
        collections=(PackCollection(ref="c", name="C", item_refs=("demo:zzz",)),),
    )
    bad_type = _plain(
        "e2",
        requires=("demo",),
        connections=(
            PackConnection(source_ref="a", target_ref="demo:a", type_ref="demo:rel"),
        ),
    )
    with pytest.raises(
        InvalidPackError, match=r"demo:zzz, which demo does not define as an item$"
    ):
        validate_catalogue({"demo": base, "e1": bad_item})
    with pytest.raises(
        InvalidPackError,
        match="demo:rel, which demo does not define as a relationship type",
    ):
        validate_catalogue({"demo": base, "e2": bad_type})


def test_a_trailing_newline_in_an_id_or_requires_entry_is_rejected() -> None:
    """Strict matching: no trailing newline."""
    with pytest.raises(InvalidPackError):
        _pack(id="demo\n")
    with pytest.raises(InvalidPackError):
        _addon(requires=("demo\n",))


def test_validate_catalogue_rejects_a_dangling_connection_source() -> None:
    """An external connection source the base lacks is refused."""
    addon = _plain(
        "extras",
        requires=("demo",),
        connections=(
            PackConnection(source_ref="demo:zzz", target_ref="a", type_ref="demo:rel"),
        ),
    )
    base = _plain(
        "demo",
        relationship_types=(
            PackRelationshipType(ref="rel", slug="rel", label="Rel", reverse_label="R"),
        ),
    )
    with pytest.raises(InvalidPackError, match=r"demo:zzz, which demo does not define"):
        validate_catalogue({"demo": base, "extras": addon})
