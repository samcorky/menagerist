"""RandomNode: a random item from what the list would show."""

import uuid
from datetime import date

import pytest

from app.modules.graph.adapters.persistence.in_memory_collection_members import (
    InMemoryCollectionMembers,
)
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
from app.modules.graph.application.list_nodes import ListNodes, ListNodesQuery
from app.modules.graph.application.random_node import RandomNode
from app.modules.graph.domain.errors import CollectionNotFoundError, NodeNotFoundError
from app.modules.graph.domain.node import Node
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import Actor

ALICE = uuid.UUID(int=1)
BOB = uuid.UUID(int=2)
AS_ALICE = Actor(id=ALICE, roles=frozenset({"member"}))
FILMS = {
    "v": 1,
    "where": {"op": "and", "children": [{"kind": "type", "in": ["film"]}]},
    "sort": [],
}


class World:
    """Repositories, a collection source and the use case over them."""

    def __init__(self) -> None:
        self.repos = GraphRepos(
            nodes=InMemoryNodeRepository(),
            edges=InMemoryEdgeRepository(),
            node_types=InMemoryNodeTypeRepository(),
            edge_types=InMemoryEdgeTypeRepository(),
        )
        self.members = InMemoryCollectionMembers()
        guard = InMemoryAccessGuard()
        lister = ListNodes(
            self.repos, guard, self.members, today=lambda: date(2026, 10, 29)
        )
        self.use_case = RandomNode(self.repos, guard, lister)

    async def item(
        self, name: str, *, owner: uuid.UUID = ALICE, type: str = "film"
    ) -> Node:
        """Store an item and return it."""
        node = Node.create(owner_id=owner, name=name, type=type)
        await self.repos.nodes.add(node)
        return node


@pytest.fixture
def world() -> World:
    """An empty world."""
    return World()


async def test_picks_one_of_the_callers_own_items(world: World) -> None:
    """Only the caller's own items are candidates."""
    mine = await world.item("Mine")
    await world.item("Theirs", owner=BOB)

    picked = await world.use_case.handle(ListNodesQuery(), AS_ALICE)

    assert picked.id == mine.id


async def test_nothing_to_pick_is_not_found(world: World) -> None:
    """With no matching item there is nothing to return, which is a not-found."""
    await world.item("Theirs", owner=BOB)
    with pytest.raises(NodeNotFoundError, match="No item matches"):
        await world.use_case.handle(ListNodesQuery(), AS_ALICE)


async def test_respects_the_list_filters(world: World) -> None:
    """The type filter narrows the pick like the list."""
    book = await world.item("A book", type="book")
    await world.item("A film")

    picked = await world.use_case.handle(ListNodesQuery(type="book"), AS_ALICE)

    assert picked.id == book.id


async def test_picks_from_a_static_collection(world: World) -> None:
    """Only the collection's members are candidates."""
    inside = await world.item("Inside")
    await world.item("Outside")
    collection = uuid.uuid7()
    world.members.add_collection(collection, [inside.id], owner_id=ALICE)

    picked = await world.use_case.handle(
        ListNodesQuery(collection=collection), AS_ALICE
    )

    assert picked.id == inside.id


async def test_picks_from_a_smart_collection(world: World) -> None:
    """A smart collection's saved query decides the candidates."""
    film = await world.item("Film")
    await world.item("Book", type="book")
    collection = uuid.uuid7()
    world.members.add_smart_collection(collection, FILMS, owner_id=ALICE)

    picked = await world.use_case.handle(
        ListNodesQuery(collection=collection), AS_ALICE
    )

    assert picked.id == film.id


async def test_a_smart_collection_with_a_stale_definition_has_nothing(
    world: World,
) -> None:
    """A definition that no longer validates matches nothing, as in the list."""
    await world.item("Film")
    collection = uuid.uuid7()
    world.members.add_smart_collection(collection, {"v": 99}, owner_id=ALICE)

    with pytest.raises(NodeNotFoundError):
        await world.use_case.handle(ListNodesQuery(collection=collection), AS_ALICE)


async def test_an_unknown_collection_is_not_found(world: World) -> None:
    """A collection that does not exist is reported, not treated as empty."""
    with pytest.raises(CollectionNotFoundError):
        await world.use_case.handle(ListNodesQuery(collection=uuid.uuid7()), AS_ALICE)
