from typing import Any

import pytest

from app.modules.transfer.adapters.codecs.menagerist_bundle import MenageristBundleCodec
from app.modules.transfer.application.codecs import CodecRegistry
from app.modules.transfer.domain.bundle import Bundle, BundleItemType, BundlePreset
from app.modules.transfer.domain.errors import InvalidBundleError, UnknownFormatError

CODEC = MenageristBundleCodec()

_EMPTY_SECTIONS: dict[str, Any] = {
    "relationship_types": [],
    "item_types": [],
    "items": [],
    "connections": [],
    "collections": [],
}


def _preset(**change: object) -> dict[str, Any]:
    preset: dict[str, Any] = {
        "ref": "grades",
        "kind": "choice_list",
        "label": "Grades",
        "description": "Mint to poor.",
        "definition": {"options": ["Mint"]},
    }
    preset.update(change)
    return {k: v for k, v in preset.items() if v is not ...}


def _type(**change: object) -> dict[str, Any]:
    entry: dict[str, Any] = {"ref": "record", "slug": "record", "label": "Record"}
    entry.update(change)
    return entry


def _rel(**change: object) -> dict[str, Any]:
    return _type(ref="wrote", slug="wrote", label="Wrote", **change)


def _file(*presets: object, **change: object) -> dict[str, Any]:
    data: dict[str, Any] = {
        "format": "menagerist-bundle",
        "version": 1,
        "presets": list(presets),
    }
    data.update(change)
    return data


def test_a_file_decodes_and_encodes_back_the_same() -> None:
    """A file reads into a bundle of presets and writes back unchanged."""
    data = _file(_preset(), _preset(ref="other", description=None))

    bundle = CODEC.decode(data)

    assert bundle.id == "menagerist-bundle"
    assert [(p.ref, p.label, p.description) for p in bundle.presets] == [
        ("grades", "Grades", "Mint to poor."),
        ("other", "Grades", None),
    ]
    assert CODEC.encode(bundle) == {**data, "version": 3, **_EMPTY_SECTIONS}


def test_a_preset_may_leave_out_its_description() -> None:
    """`description` is optional."""
    bundle = CODEC.decode(_file(_preset(description=...)))
    assert bundle.presets[0].description is None


def test_a_file_without_presets_is_an_empty_bundle() -> None:
    """`presets` is optional."""
    assert CODEC.decode({"format": "menagerist-bundle", "version": 1}).presets == ()


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (_file(version=4), "unsupported menagerist-bundle version 4"),
        (_file(version=2, items=[]), "unknown keys"),
        (_file(item_types=[]), "unknown keys"),
        (_file(version=2, item_types={}), "item_types must be a list"),
        (_file(version=2, item_types=["x"]), r"item_types\[0\] must be an object"),
        (_file(version=2, item_types=[{"ref": "t"}]), "needs label, slug"),
        (
            _file(version=2, item_types=[_type(slug=5)]),
            "item_types\\[0\\] slug must be text",
        ),
        (
            _file(version=2, item_types=[_type(attributes_schema=[])]),
            "attributes_schema must be an object",
        ),
        (
            _file(version=2, relationship_types=[_rel(directional="yes")]),
            "directional must be true or false",
        ),
        (
            _file(version=2, relationship_types=[_rel(colour="red")]),
            "unknown keys",
        ),
        (_file(extra=1), "unknown keys"),
        (_file(presets={}), "presets must be a list"),
        (_file("text"), r"presets\[0\] must be an object"),
        (_file(_preset(kind=...)), "needs kind"),
        (_file(_preset(colour="red")), "unknown keys"),
        (_file(_preset(ref="Bad Ref")), "ref must be lowercase"),
        (_file(_preset(ref=5)), "ref must be text"),
        (_file(_preset(label=None)), "label must be text"),
        (_file(_preset(description=5)), "description must be text"),
        (_file(_preset(definition=[])), "definition must be an object"),
        (_file(_preset(), _preset()), "each preset needs its own ref"),
    ],
)
def test_a_malformed_file_is_refused(data: dict[str, Any], message: str) -> None:
    """A malformed file is refused with what is wrong."""
    with pytest.raises(InvalidBundleError, match=message):
        CODEC.decode(data)


def test_types_sharing_a_ref_are_refused() -> None:
    """Refs are unique within each kind of a bundle."""
    book = BundleItemType(ref="book", slug="book", label="Book")
    with pytest.raises(InvalidBundleError, match="each item type"):
        Bundle(id="b", item_types=(book, book))


def test_the_registry_finds_a_codec_by_format() -> None:
    """The registry returns the codec for a format, and refuses an unknown one."""
    registry = CodecRegistry([CODEC])

    assert registry.get("menagerist-bundle") is CODEC
    assert registry.formats == ("menagerist-bundle",)
    for unknown in ("menagerist-presets", None):
        with pytest.raises(UnknownFormatError, match="'menagerist-bundle'"):
            registry.get(unknown)


def test_two_codecs_for_one_format_are_a_mistake() -> None:
    """Registering one format twice fails at start-up."""
    with pytest.raises(ValueError, match="two codecs"):
        CodecRegistry([CODEC, MenageristBundleCodec()])


def test_a_bundle_preset_round_trips_through_encode() -> None:
    """Encoding writes every field of a preset."""
    preset = BundlePreset(ref="x", kind="field", label="X", definition={"a": 1})
    encoded = CODEC.encode(Bundle(id="b", presets=(preset,)))
    assert encoded["presets"] == [
        {
            "ref": "x",
            "kind": "field",
            "label": "X",
            "description": None,
            "definition": {"a": 1},
        }
    ]


def test_a_version_two_file_carries_types() -> None:
    """Types decode with their optional parts, and encode back as written."""
    data = _file(
        _preset(),
        version=2,
        relationship_types=[
            {
                "ref": "wrote",
                "slug": "wrote",
                "label": "Wrote",
                "reverse_label": "Written by",
                "description": None,
                "directional": False,
                "attributes_schema": None,
            }
        ],
        item_types=[
            {
                "ref": "record",
                "slug": "record",
                "label": "Record",
                "description": "A disc.",
                "attributes_schema": {"type": "object"},
                "icon": "disc",
                "colour": "blue",
            }
        ],
    )

    bundle = CODEC.decode(data)

    assert [(t.slug, t.icon, t.colour) for t in bundle.item_types] == [
        ("record", "disc", "blue")
    ]
    assert [(r.reverse_label, r.directional) for r in bundle.relationship_types] == [
        ("Written by", False)
    ]
    assert CODEC.encode(bundle) == {
        **data,
        "version": 3,
        "items": [],
        "connections": [],
        "collections": [],
    }


def _item(**change: object) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "ref": "blue",
        "type_ref": "record",
        "name": "Kind of Blue",
        "description": None,
        "attributes": {"year": 1959},
        "tags": ["jazz"],
        "extra_schema": None,
    }
    entry.update(change)
    return entry


def _connection(**change: object) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "source_ref": "blue",
        "target_ref": "love",
        "type_ref": "wrote",
        "attributes": {},
    }
    entry.update(change)
    return entry


def _collection(**change: object) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "ref": "shelf",
        "name": "Jazz shelf",
        "description": None,
        "item_refs": ["blue"],
        "definition": None,
    }
    entry.update(change)
    return entry


def _v3(**change: object) -> dict[str, Any]:
    data = _file(
        version=3,
        relationship_types=[_rel()],
        item_types=[_type()],
        items=[_item(), _item(ref="love", name="A Love Supreme", tags=[])],
        connections=[_connection()],
        collections=[_collection()],
    )
    data.update(change)
    return data


def test_a_version_three_file_carries_items_connections_and_collections() -> None:
    """Items, connections and collections decode and encode back as written."""
    data = _v3(
        collections=[
            _collection(),
            _collection(
                ref="smart",
                name="Records",
                item_refs=[],
                definition={"v": 1, "where": {"kind": "type", "in": ["record"]}},
            ),
        ]
    )

    bundle = CODEC.decode(data)

    first = bundle.items[0]
    assert (first.name, first.type_ref, first.tags) == (
        "Kind of Blue",
        "record",
        ("jazz",),
    )
    assert [(c.source_ref, c.target_ref) for c in bundle.connections] == [
        ("blue", "love")
    ]
    assert [c.item_refs for c in bundle.collections] == [("blue",), ()]
    written = CODEC.encode(bundle)
    for section in ("items", "connections", "collections"):
        assert written[section] == data[section]
    assert written["version"] == 3


def test_an_item_and_a_connection_may_leave_out_what_is_optional() -> None:
    """Only the names and refs are needed."""
    bundle = CODEC.decode(
        _v3(
            items=[
                {"ref": "blue", "type_ref": "record", "name": "A"},
                {"ref": "love", "type_ref": "record", "name": "B"},
            ],
            connections=[
                {"source_ref": "blue", "target_ref": "love", "type_ref": "wrote"}
            ],
            collections=[],
        )
    )

    assert bundle.items[0].attributes == {}
    assert bundle.items[0].tags == ()
    assert bundle.connections[0].attributes == {}


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (_v3(items=["x"]), r"items\[0\] must be an object"),
        (_v3(items=[{"ref": "blue"}]), "needs name, type_ref"),
        (_v3(items=[_item(tags="jazz")]), "tags must be a list of text"),
        (_v3(items=[_item(tags=[5])]), "tags must be a list of text"),
        (_v3(items=[_item(attributes=[])]), "attributes must be an object"),
        (_v3(items=[_item(extra_schema=[])]), "extra_schema must be an object"),
        (_v3(items=[_item(name=5)]), "name must be text"),
        (_v3(items=[_item(type_ref="Bad Ref")]), "type_ref must be lowercase"),
        (_v3(items=[_item(colour="red")]), "unknown keys"),
        (_v3(items=[_item(type_ref="album")]), "type 'album', not in the file"),
        (_v3(connections=["x"]), r"connections\[0\] must be an object"),
        (_v3(connections=[{"source_ref": "blue"}]), "needs target_ref, type_ref"),
        (_v3(connections=[_connection(colour="red")]), "unknown keys"),
        (_v3(connections=[_connection(type_ref="owns")]), "type 'owns'"),
        (_v3(connections=[_connection(target_ref="gone")]), "not in the file"),
        (_v3(connections=[_connection(target_ref="blue")]), "to itself"),
        (_v3(collections=[_collection(item_refs="blue")]), "item_refs must be a list"),
        (_v3(collections=[_collection(item_refs=[5])]), "item_refs must be text"),
        (_v3(collections=[_collection(item_refs=["gone"])]), "item 'gone'"),
        (_v3(collections=[_collection(item_refs=[])]), "either item_refs or a def"),
        (
            _v3(collections=[_collection(definition={"v": 1})]),
            "either item_refs or a def",
        ),
        (_v3(collections=[_collection(definition=[])]), "definition must be an obj"),
        (
            _v3(
                collections=[
                    _collection(
                        item_refs=[],
                        definition={"where": {"kind": "collection", "id": "x"}},
                    )
                ]
            ),
            "a collection condition cannot be in a bundle",
        ),
    ],
)
def test_a_malformed_version_three_file_is_refused(
    data: dict[str, Any], message: str
) -> None:
    """Items, connections and collections are checked against each other."""
    with pytest.raises(InvalidBundleError, match=message):
        CODEC.decode(data)


def test_a_type_may_leave_out_what_is_optional() -> None:
    """Only `ref`, `slug` and `label` are needed; a connection type reads one way."""
    bundle = CODEC.decode(
        _file(version=2, item_types=[_type()], relationship_types=[_rel()])
    )

    assert bundle.item_types[0].icon is None
    assert bundle.relationship_types[0].directional is True
