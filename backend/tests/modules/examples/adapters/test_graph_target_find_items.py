"""`GraphPackTarget.find_items_by_field`."""

import uuid
from typing import TYPE_CHECKING

from app.modules.graph.domain.node import Node

if TYPE_CHECKING:
    from tests.modules.examples.conftest import MakeWorld

OTHER = uuid.UUID(int=0xB2)


async def test_finds_items_by_attribute_value_for_the_actor_only(
    make_world: MakeWorld,
) -> None:
    """Finds items by attribute value for the actor only."""
    world = make_world()
    mine = Node.create(
        owner_id=world.actor.id, name="Alien", type="film", attributes={"upc": "0123"}
    )
    theirs = Node.create(
        owner_id=OTHER, name="Alien", type="film", attributes={"upc": "0123"}
    )
    for node in (mine, theirs):
        await world.graph_repos.nodes.add(node)

    assert await world.graph.find_items_by_field("film", "upc", "0123") == [mine.id]
    assert await world.graph.find_items_by_field("film", "upc", "nope") == []


async def test_name_is_matched_as_the_item_name(make_world: MakeWorld) -> None:
    """Name is matched as the item name."""
    world = make_world()
    alien = Node.create(owner_id=world.actor.id, name="Alien", type="film")
    await world.graph_repos.nodes.add(alien)

    assert await world.graph.find_items_by_field("film", "name", "Alien") == [alien.id]
    assert await world.graph.find_items_by_field("film", "name", "alien") == []


async def test_limit_caps_the_matches(make_world: MakeWorld) -> None:
    """Limit caps the matches."""
    world = make_world()
    for _ in range(3):
        await world.graph_repos.nodes.add(
            Node.create(owner_id=world.actor.id, name="Alien", type="film")
        )

    assert len(await world.graph.find_items_by_field("film", "name", "Alien")) == 2
    assert (
        len(await world.graph.find_items_by_field("film", "name", "Alien", limit=3))
        == 3
    )


async def test_a_name_can_be_matched_ignoring_case(make_world: MakeWorld) -> None:
    """Ignoring case finds the item by name, but never relaxes an attribute."""
    world = make_world()
    alien = Node.create(
        owner_id=world.actor.id, name="Alien", type="film", attributes={"upc": "AB"}
    )
    await world.graph_repos.nodes.add(alien)
    find = world.graph.find_items_by_field

    assert await find("film", "name", "alien", ignore_case=True) == [alien.id]
    assert await find("film", "upc", "ab", ignore_case=True) == []
