"""`GraphPackTarget.item_type_fields` and `check_item_attributes`."""

import uuid
from typing import TYPE_CHECKING, Any

from app.modules.transfer.domain.bundle import BundleItemType

if TYPE_CHECKING:
    from tests.modules.examples.conftest import MakeWorld, World

OTHER = uuid.UUID(int=0xB2)
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "position": {
            "type": "string",
            "title": "Position and pen",
            "x-menagerist": {"kind": "text"},
        },
        "pages": {"type": "integer", "x-menagerist": {"kind": "number"}},
        "authenticated": {
            "type": "boolean",
            "title": "Authenticated",
            "x-menagerist": {"kind": "boolean"},
        },
        "grade": {
            "type": "string",
            "title": "Grade",
            "enum": ["Mint", "Good"],
            "x-menagerist": {"kind": "choice"},
        },
        "tags": {
            "type": "array",
            "title": "Marks",
            "items": {"type": "string", "enum": ["Foil", "Signed"]},
            "x-menagerist": {"kind": "multichoice"},
        },
        "signed_on": {
            "type": "string",
            "title": "Signed on",
            "pattern": "^[0-9]{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12][0-9]|3[01]))?)?$",
            "x-menagerist": {"kind": "partialdate"},
        },
        "old": {
            "type": "string",
            "title": "Old",
            "x-menagerist": {"kind": "text", "archived": True},
        },
        "value": {
            "type": "number",
            "title": "Value",
            "x-menagerist": {"kind": "money"},
        },
    },
}


async def _world_with_type(make_world: MakeWorld) -> World:
    world = make_world()
    await world.graph.create_item_type(
        BundleItemType(
            ref="signature",
            slug="signature",
            label="Signature",
            attributes_schema=SCHEMA,
        ),
        {},
    )
    return world


async def test_fields_are_described_with_kind_options_and_title(
    make_world: MakeWorld,
) -> None:
    """Each live field says its key, title, shape, kind and choices."""
    world = await _world_with_type(make_world)

    fields = await world.graph.item_type_fields("signature")

    assert fields is not None
    by_key = {f.key: f for f in fields}
    assert "old" not in by_key
    position = by_key["position"]
    assert (position.title, position.json_type, position.kind) == (
        "Position and pen",
        "string",
        "text",
    )
    assert by_key["pages"].title == "pages"
    assert by_key["grade"].options == ("Mint", "Good")
    assert not by_key["grade"].multiple
    assert by_key["tags"].options == ("Foil", "Signed")
    assert by_key["tags"].multiple
    assert by_key["signed_on"].kind == "partialdate"
    assert by_key["authenticated"].json_type == "boolean"


async def test_unsupported_kinds_are_marked_unimportable(make_world: MakeWorld) -> None:
    """A money field cannot be filled yet, and says so."""
    world = await _world_with_type(make_world)

    fields = await world.graph.item_type_fields("signature")

    assert fields is not None
    value = next(f for f in fields if f.key == "value")
    assert not value.importable
    assert value.reason == "Value cannot be imported yet"


async def test_an_unknown_type_has_no_fields(make_world: MakeWorld) -> None:
    """A type the person lacks is `None`, not empty."""
    assert await make_world().graph.item_type_fields("nope") is None


async def test_another_persons_type_is_not_visible(make_world: MakeWorld) -> None:
    """Fields are read from the actor's own types only."""
    world = await _world_with_type(make_world)
    other = world.as_actor(world.actor.__class__(id=OTHER, roles=world.actor.roles))

    assert await other.graph.item_type_fields("signature") is None


async def test_valid_attributes_have_no_problems(make_world: MakeWorld) -> None:
    """Good values give an empty list."""
    world = await _world_with_type(make_world)
    problems = await world.graph.check_item_attributes(
        "signature", {"grade": "Mint", "signed_on": "2019-08", "pages": 3}
    )
    assert problems == []


async def test_each_problem_names_the_field_by_its_title(make_world: MakeWorld) -> None:
    """A wrong value is reported with the field's title."""
    world = await _world_with_type(make_world)

    problems = await world.graph.check_item_attributes(
        "signature", {"grade": "Fair", "signed_on": "soon"}
    )

    assert len(problems) == 2
    assert any(p.startswith("Grade: ") for p in problems)
    assert any(p.startswith("Signed on: ") for p in problems)
