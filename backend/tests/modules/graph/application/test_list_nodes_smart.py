"""ListNodes over a smart collection: its saved query ANDed with the list filters."""

import uuid
from datetime import date
from typing import Any

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
from app.modules.graph.application.count_nodes import CountNodes
from app.modules.graph.application.list_nodes import ListNodes, ListNodesQuery
from app.modules.graph.domain.errors import CollectionNotFoundError
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import Actor

ALICE = uuid.UUID(int=1)
BOB = uuid.UUID(int=2)
AS_ALICE = Actor(id=ALICE, roles=frozenset({"member"}))
AS_BOB = Actor(id=BOB, roles=frozenset({"member"}))
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "rating": {"type": "number", "x-menagerist": {"kind": "rating"}},
        "year": {"type": "number", "x-menagerist": {"kind": "number"}},
    },
}


def _rating(op: str, value: object) -> dict[str, Any]:
    return {"kind": "field", "type": "film", "key": "rating", "op": op, "value": value}


def _query(*children: dict[str, Any]) -> dict[str, Any]:
    where = {"op": "and", "children": list(children)} if children else None
    return {"v": 1, "where": where, "sort": [{"by": "name", "dir": "desc"}]}


class World:
    """Graph repositories, a members source and the use case over them."""

    def __init__(self) -> None:
        self.repos = GraphRepos(
            nodes=InMemoryNodeRepository(),
            edges=InMemoryEdgeRepository(),
            node_types=InMemoryNodeTypeRepository(),
            edge_types=InMemoryEdgeTypeRepository(),
        )
        self.members = InMemoryCollectionMembers()
        self.use_case = ListNodes(
            self.repos,
            InMemoryAccessGuard(),
            self.members,
            today=lambda: date(2026, 10, 17),
        )

    async def setup(self) -> None:
        """Add the film and book item types."""
        await self.repos.node_types.add(
            NodeType.create(slug="film", label="Film", attributes_schema=SCHEMA)
        )
        await self.repos.node_types.add(NodeType.create(slug="book", label="Book"))

    async def item(
        self,
        name: str,
        *,
        owner: uuid.UUID = ALICE,
        type: str = "film",
        rating: int | None = None,
        favourite: bool = False,
    ) -> Node:
        """Store an item and return it."""
        attributes = {} if rating is None else {"rating": rating}
        node = Node.create(
            owner_id=owner,
            name=name,
            type=type,
            attributes=attributes,
            favourite=favourite,
        )
        await self.repos.nodes.add(node)
        return node

    def smart(
        self, definition: dict[str, Any], *, owner: uuid.UUID = ALICE
    ) -> uuid.UUID:
        """Register a smart collection and return its id."""
        collection_id = uuid.uuid7()
        self.members.add_smart_collection(collection_id, definition, owner_id=owner)
        return collection_id


@pytest.fixture
async def world() -> World:
    """A world with the item types in place."""
    w = World()
    await w.setup()
    return w


async def test_lists_exactly_the_matching_items_in_id_order(world: World) -> None:
    """The saved query decides membership; the saved sort is ignored (R19)."""
    good = [await world.item(f"Good {i}", rating=4 + i % 2) for i in range(3)]
    await world.item("Poor", rating=1)
    await world.item("Unrated")
    collection = world.smart(_query(_rating(">=", 4)))

    result = await world.use_case.handle(
        ListNodesQuery(collection=collection), AS_ALICE
    )

    assert result.items == sorted(good, key=lambda n: n.id)
    assert result.total == 3


async def test_an_empty_where_matches_every_item(world: World) -> None:
    """A definition with no conditions holds every live item of the viewer."""
    mine = [await world.item("One"), await world.item("Two", type="book")]
    await world.item("Bob's", owner=BOB)
    collection = world.smart(_query())

    result = await world.use_case.handle(
        ListNodesQuery(collection=collection), AS_ALICE
    )

    assert result.items == sorted(mine, key=lambda n: n.id)
    assert result.total == 2


async def test_filters_are_anded_with_the_saved_query(world: World) -> None:
    """q, type and favourite narrow the saved query, never widen it."""
    await world.item("Alien", rating=5, favourite=True)
    await world.item("Aliens", rating=4)
    await world.item("Alien Nation", rating=1, favourite=True)
    await world.item("Alien Book", type="book", favourite=True)
    collection = world.smart(_query(_rating(">=", 4)))

    async def names(**filters: Any) -> tuple[set[str], int]:  # noqa: ANN401
        result = await world.use_case.handle(
            ListNodesQuery(collection=collection, **filters), AS_ALICE
        )
        return {n.name for n in result.items}, result.total

    assert await names(q="alien") == ({"Alien", "Aliens"}, 2)
    assert await names(q="nation") == (set(), 0)
    assert await names(type="film") == ({"Alien", "Aliens"}, 2)
    assert await names(type="book") == (set(), 0)
    assert await names(favourite=True) == ({"Alien"}, 1)
    assert await names(favourite=False) == ({"Aliens"}, 1)
    assert await names(q="alien", type="film", favourite=True) == ({"Alien"}, 1)


async def test_pages_by_id_across_a_boundary(world: World) -> None:
    """`after` and `limit` walk the matches in id order with a steady total."""
    good = [await world.item(f"Good {i}", rating=5) for i in range(5)]
    await world.item("Poor", rating=1)
    collection = world.smart(_query(_rating("=", 5)))
    ordered = sorted(good, key=lambda n: n.id)

    first = await world.use_case.handle(
        ListNodesQuery(collection=collection, limit=2), AS_ALICE
    )
    second = await world.use_case.handle(
        ListNodesQuery(collection=collection, limit=2, after=first.items[-1].id),
        AS_ALICE,
    )
    last = await world.use_case.handle(
        ListNodesQuery(collection=collection, limit=2, after=second.items[-1].id),
        AS_ALICE,
    )

    assert first.items == ordered[:2]
    assert second.items == ordered[2:4]
    assert last.items == ordered[4:]
    assert first.total == second.total == last.total == 5


async def test_never_returns_another_persons_items(world: World) -> None:
    """The viewer's scope applies last: matching items of others never appear."""
    mine = await world.item("Mine", rating=5)
    await world.item("Bob's", owner=BOB, rating=5)
    collection = world.smart(_query(_rating("=", 5)))

    result = await world.use_case.handle(
        ListNodesQuery(collection=collection), AS_ALICE
    )

    assert result.items == [mine]
    assert result.total == 1


async def test_another_persons_smart_collection_is_not_found(world: World) -> None:
    """Bob cannot list Alice's smart collection, even though it would match his."""
    await world.item("Bob's", owner=BOB, rating=5)
    collection = world.smart(_query(_rating("=", 5)))

    with pytest.raises(CollectionNotFoundError):
        await world.use_case.handle(ListNodesQuery(collection=collection), AS_BOB)


async def test_a_stale_field_matches_nothing(world: World) -> None:
    """A condition on a removed field lists nothing rather than failing."""
    await world.item("Good", rating=5)
    gone = {"kind": "field", "type": "film", "key": "gone", "op": "=", "value": 1}
    collection = world.smart(_query(gone))

    result = await world.use_case.handle(
        ListNodesQuery(collection=collection), AS_ALICE
    )

    assert result.items == []
    assert result.total == 0


@pytest.mark.parametrize(
    "definition",
    [
        {"v": 9},
        _query(_rating("~", "five")),
        {"v": 1, "where": "everything"},
    ],
    ids=["unsupported-version", "operator-no-longer-fits", "malformed"],
)
async def test_a_definition_that_no_longer_validates_lists_nothing(
    world: World, definition: dict[str, Any]
) -> None:
    """A stored query that no longer validates degrades to an empty list."""
    await world.item("Good", rating=5)
    collection = world.smart(definition)

    result = await world.use_case.handle(
        ListNodesQuery(collection=collection, q="good"), AS_ALICE
    )

    assert result.items == []
    assert result.total == 0


async def test_without_a_collection_q_still_uses_the_plain_list(world: World) -> None:
    """With no collection, q searches every type, including ones excluding nothing."""
    await world.item("Alien", rating=5)
    await world.item("Alien Book", type="book")

    result = await world.use_case.handle(ListNodesQuery(q="alien"), AS_ALICE)

    assert {n.name for n in result.items} == {"Alien", "Alien Book"}
    assert result.total == 2


async def test_smart_total_with_text_search_is_capped(world: World) -> None:
    """With `q`, a smart collection's total stops at the cap; without, it is exact."""
    capped = ListNodes(
        world.repos,
        InMemoryAccessGuard(),
        world.members,
        today=lambda: date(2026, 10, 17),
        total_cap=3,
    )
    for i in range(5):
        await world.item(f"Coin {i}", rating=5)
    collection = world.smart(_query(_rating(">=", 4)))

    searched = await capped.handle(
        ListNodesQuery(collection=collection, q="coin", limit=2), AS_ALICE
    )
    plain = await capped.handle(ListNodesQuery(collection=collection), AS_ALICE)

    assert (searched.total, searched.total_capped, len(searched.items)) == (3, True, 2)
    assert (plain.total, plain.total_capped) == (5, False)


async def test_count_exact_is_uncapped_and_scoped(world: World) -> None:
    """CountNodes counts a smart collection's matches fully, for the caller only."""
    counter = CountNodes(world.repos, InMemoryAccessGuard(), world.use_case)
    for i in range(5):
        await world.item(f"Coin {i}", rating=5)
    await world.item("Coin Bob", owner=BOB, rating=5)
    mine = world.smart(_query(_rating(">=", 4)))
    stale = world.smart(_query(_rating("nonsense", 4)))

    assert await counter.handle(ListNodesQuery(collection=mine), AS_ALICE) == 5
    assert await counter.handle(ListNodesQuery(collection=mine, q="bob"), AS_ALICE) == 0
    assert await counter.handle(ListNodesQuery(collection=stale), AS_ALICE) == 0
    assert await counter.handle(ListNodesQuery(q="coin"), AS_ALICE) == 5
    assert await counter.handle(ListNodesQuery(q="coin"), AS_BOB) == 1
