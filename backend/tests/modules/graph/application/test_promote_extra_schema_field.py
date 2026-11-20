import uuid
from typing import Any

import pytest

from app.modules.graph.adapters.persistence.in_memory_edge_repository import (
    InMemoryEdgeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_edge_type_repository import (
    InMemoryEdgeTypeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_node_type_repository import (
    InMemoryNodeTypeRepository,
)
from app.modules.graph.application.permissions import GraphPermission
from app.modules.graph.application.promote_extra_schema_field import (
    PromotedField,
    PromoteExtraSchemaField,
    PromoteExtraSchemaFieldCommand,
)
from app.modules.graph.domain.errors import (
    InvalidSchemaError,
    NodeNotFoundError,
    NodeTypeNotFoundError,
)
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access import Content
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

_OWNER = uuid.UUID(int=1)
_CONDITION = {"title": "Condition", "type": "string"}


def _overlay(**properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": properties}


class _World:
    """An item type `film`, its items, and the use case wired to them."""

    def __init__(self, type_properties: dict[str, Any] | None = None) -> None:
        self.nodes = InMemoryNodeRepository()
        self.node_types = InMemoryNodeTypeRepository()
        self.film = NodeType.create(
            owner_id=_OWNER,
            slug="film",
            label="Film",
            attributes_schema=_overlay(**(type_properties or {})),
        )
        self.uow = InMemoryUnitOfWork(
            GraphRepos(
                nodes=self.nodes,
                edges=InMemoryEdgeRepository(),
                node_types=self.node_types,
                edge_types=InMemoryEdgeTypeRepository(),
            )
        )

    async def setup(self) -> None:
        await self.node_types.add(self.film)

    async def item(
        self,
        name: str,
        *,
        type: str = "film",
        attributes: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> Node:
        node = Node.create(
            owner_id=_OWNER,
            name=name,
            type=type,
            attributes=attributes or {},
            extra_schema=extra,
        )
        await self.nodes.add(node)
        return node

    async def promote(
        self, key: str, node_id: uuid.UUID | None = None
    ) -> PromotedField:
        return await PromoteExtraSchemaField(self.uow, InMemoryAccessGuard()).handle(
            PromoteExtraSchemaFieldCommand(
                node_type_id=self.film.id, key=key, node_id=node_id
            ),
            SYSTEM_ACTOR,
        )

    async def type_properties(self) -> dict[str, Any]:
        saved = await self.node_types.get(self.film.id, scope=ContentFilter.everyone())
        assert saved is not None
        assert saved.attributes_schema is not None
        properties: dict[str, Any] = saved.attributes_schema["properties"]
        return properties

    async def overlay_of(self, node: Node) -> dict[str, Any]:
        saved = await self.nodes.get(node.id, scope=ContentFilter.everyone())
        assert saved is not None
        assert saved.extra_schema is not None
        overlay: dict[str, Any] = saved.extra_schema
        return overlay


async def _world(type_properties: dict[str, Any] | None = None) -> _World:
    world = _World(type_properties)
    await world.setup()
    return world


async def test_moves_the_field_off_every_item_of_the_type() -> None:
    """The field joins the type and leaves each item's overlay; values stay."""
    world = await _world({"title": {"title": "Title", "type": "string"}})
    alien = await world.item(
        "Alien", attributes={"condition": "Mint"}, extra=_overlay(condition=_CONDITION)
    )
    heat = await world.item(
        "Heat", attributes={"condition": "Worn"}, extra=_overlay(condition=_CONDITION)
    )

    promoted = await world.promote("condition")

    assert promoted.items == 2
    assert (await world.type_properties())["condition"] == _CONDITION
    for node, value in ((alien, "Mint"), (heat, "Worn")):
        assert (await world.overlay_of(node))["properties"] == {}
        saved = await world.nodes.get(node.id, scope=ContentFilter.everyone())
        assert saved is not None
        assert saved.attributes["condition"] == value
    assert world.uow.committed


async def test_leaves_the_other_overlay_fields_and_other_types_alone() -> None:
    """Only the promoted key moves, and only on items of this type."""
    world = await _world()
    signed = {"title": "Signed", "type": "boolean"}
    alien = await world.item(
        "Alien", extra=_overlay(condition=_CONDITION, signed=signed)
    )
    book = await world.item("Dune", type="book", extra=_overlay(condition=_CONDITION))

    await world.promote("condition")

    assert (await world.overlay_of(alien))["properties"] == {"signed": signed}
    assert (await world.overlay_of(book))["properties"] == {"condition": _CONDITION}


async def test_drops_the_key_from_the_overlay_required_list() -> None:
    """A field the overlay recommended is no longer listed there once moved."""
    world = await _world()
    alien = await world.item(
        "Alien",
        extra={
            **_overlay(condition=_CONDITION, signed={"type": "boolean"}),
            "x-menagerist": {"required": ["condition", "signed"]},
        },
    )

    await world.promote("condition")

    assert (await world.overlay_of(alien))["x-menagerist"]["required"] == ["signed"]


async def test_the_named_item_s_definition_wins() -> None:
    """Promoting from an item uses that item's title, even if fewer items share it."""
    world = await _world()
    for name in ("Alien", "Heat"):
        await world.item(name, extra=_overlay(condition=_CONDITION))
    mine = await world.item(
        "Ran", extra=_overlay(condition={"title": "State", "type": "string"})
    )

    promoted = await world.promote("condition", node_id=mine.id)

    assert promoted.items == 3
    assert (await world.type_properties())["condition"]["title"] == "State"


async def test_without_an_item_the_most_common_definition_wins() -> None:
    """Promoting from the type uses the definition most of its items have."""
    world = await _world()
    state = {"title": "State", "type": "string"}
    await world.item("Ran", extra=_overlay(condition=state))
    for name in ("Alien", "Heat"):
        await world.item(name, extra=_overlay(condition=_CONDITION))

    await world.promote("condition")

    assert (await world.type_properties())["condition"]["title"] == "Condition"


async def test_choice_options_from_every_item_are_kept() -> None:
    """A choice field keeps every item's options, so no stored value breaks."""
    world = await _world()

    def grade(*options: str) -> dict[str, Any]:
        return {
            "title": "Grade",
            "type": "string",
            "enum": list(options),
            "x-menagerist": {"kind": "choice"},
        }

    await world.item("Alien", extra=_overlay(grade=grade("Mint", "Good")))
    await world.item("Heat", extra=_overlay(grade=grade("Good", "Poor")))
    await world.item("Ran", extra=_overlay(grade=grade("Mint", "Good")))

    await world.promote("grade")

    assert (await world.type_properties())["grade"]["enum"] == ["Mint", "Good", "Poor"]


async def test_multichoice_options_from_every_item_are_kept() -> None:
    """A multi-choice field's options sit under `items` and are combined there."""
    world = await _world()

    def tags(*options: str) -> dict[str, Any]:
        return {
            "type": "array",
            "items": {"type": "string", "enum": list(options)},
            "x-menagerist": {"kind": "multichoice"},
        }

    await world.item("Alien", extra=_overlay(region=tags("UK", "US")))
    await world.item("Heat", extra=_overlay(region=tags("JP")))

    await world.promote("region")

    assert (await world.type_properties())["region"]["items"]["enum"] == [
        "UK",
        "US",
        "JP",
    ]


async def test_items_that_disagree_on_the_kind_refuse_the_promotion() -> None:
    """A key that is text on one item and a number on another is not one field."""
    world = await _world()
    alien = await world.item("Alien", extra=_overlay(copies={"type": "string"}))
    await world.item("Heat", extra=_overlay(copies={"type": "number"}))

    with pytest.raises(InvalidSchemaError, match="1 item"):
        await world.promote("copies")

    assert "copies" not in await world.type_properties()
    assert "copies" in (await world.overlay_of(alien))["properties"]


async def test_a_key_no_item_has_raises() -> None:
    """There is nothing to promote when no item of the type carries the key."""
    world = await _world()
    await world.item("Alien")

    with pytest.raises(InvalidSchemaError):
        await world.promote("condition")


async def test_a_named_item_without_the_key_raises() -> None:
    """Promoting from an item needs that item to carry the field."""
    world = await _world()
    await world.item("Alien", extra=_overlay(condition=_CONDITION))
    bare = await world.item("Heat")

    with pytest.raises(InvalidSchemaError):
        await world.promote("condition", node_id=bare.id)


async def test_key_already_on_the_type_raises() -> None:
    """Promoting a key that already exists on the item type raises."""
    world = await _world({"condition": _CONDITION})
    await world.item("Alien", extra=_overlay(condition=_CONDITION))

    with pytest.raises(InvalidSchemaError):
        await world.promote("condition")


async def test_node_not_found_raises() -> None:
    """Promoting from a missing item raises."""
    world = await _world()

    with pytest.raises(NodeNotFoundError):
        await world.promote("condition", node_id=uuid.uuid7())


async def test_node_type_not_found_raises() -> None:
    """Promoting onto a missing item type raises."""
    world = _World()
    await world.item("Alien", extra=_overlay(condition=_CONDITION))

    with pytest.raises(NodeTypeNotFoundError):
        await world.promote("condition")


async def test_reads_the_items_in_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every item is moved even when there are more than one page of them."""
    from app.modules.graph.application import promote_extra_schema_field

    monkeypatch.setattr(promote_extra_schema_field, "_PAGE", 2)
    world = await _world()
    items = [
        await world.item(f"Film {n}", extra=_overlay(condition=_CONDITION))
        for n in range(5)
    ]

    promoted = await world.promote("condition")

    assert promoted.items == 5
    for node in items:
        assert (await world.overlay_of(node))["properties"] == {}


async def test_editing_the_items_needs_item_write_too() -> None:
    """A token that may edit types but not items cannot strip items' fields (R8)."""
    checked: list[object] = []

    class Recording(InMemoryAccessGuard):
        async def check(self, actor: Any, access: Any) -> None:  # noqa: ANN401
            checked.append(access)
            await super().check(actor, access)

    world = await _world()
    await world.item("Alien", extra=_overlay(condition=_CONDITION))

    await PromoteExtraSchemaField(world.uow, Recording()).handle(
        PromoteExtraSchemaFieldCommand(node_type_id=world.film.id, key="condition"),
        SYSTEM_ACTOR,
    )

    assert Content(GraphPermission.ITEM_WRITE) in checked


async def test_a_choice_from_a_list_has_no_options_to_combine() -> None:
    """A choice drawing on a choice list stores no options; the others still combine."""
    world = await _world()
    from_list = {"type": "string", "x-menagerist": {"kind": "choice", "list": "grades"}}
    listed = {"type": "string", "enum": ["Mint"], "x-menagerist": {"kind": "choice"}}
    await world.item("Alien", extra=_overlay(grade=listed))
    await world.item("Heat", extra=_overlay(grade=from_list))
    mine = await world.item("Ran", extra=_overlay(grade=listed))

    await world.promote("grade", node_id=mine.id)

    assert (await world.type_properties())["grade"]["enum"] == ["Mint"]
