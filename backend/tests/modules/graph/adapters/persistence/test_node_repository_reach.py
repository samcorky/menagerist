"""`NodeRepository.reach`, against the in-memory and Postgres adapters."""

import itertools
import uuid
from typing import TYPE_CHECKING

import pytest

from app.modules.graph.adapters.persistence.edge_repository import (
    SqlAlchemyEdgeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_edge_repository import (
    InMemoryEdgeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.adapters.persistence.node_repository import (
    SqlAlchemyNodeRepository,
)
from app.modules.graph.domain.edge import Edge
from app.modules.graph.domain.node import Node
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from app.modules.graph.domain.reach import Reached
    from app.modules.graph.ports.edge_repository import EdgeRepository
    from app.modules.graph.ports.node_repository import NodeRepository

ALICE = uuid.UUID(int=101)
BOB = uuid.UUID(int=102)
A = ContentFilter.of(ALICE)
CONTAINS = "contains"


class Store:
    """Both repositories over one store, with short helpers for building graphs."""

    def __init__(self, nodes: NodeRepository, edges: EdgeRepository) -> None:
        self.nodes = nodes
        self.edges = edges

    async def item(
        self, name: str, *, owner: uuid.UUID = ALICE, deleted: bool = False
    ) -> Node:
        """Add an item."""
        node = Node.create(owner_id=owner, name=name, type=None)
        if deleted:
            node.soft_delete()
        await self.nodes.add(node)
        return node

    async def link(
        self,
        source: Node,
        target: Node,
        *,
        type_slug: str = CONTAINS,
        owner: uuid.UUID = ALICE,
        deleted: bool = False,
    ) -> None:
        """Connect two items."""
        edge = Edge.create(
            owner_id=owner, source_id=source.id, target_id=target.id, type=type_slug
        )
        if deleted:
            edge.soft_delete()
        await self.edges.add(edge)

    async def reach(
        self,
        start: Node,
        *,
        direction: str = "out",
        depth: int = 25,
        relationship: str = CONTAINS,
        scope: ContentFilter = A,
    ) -> list[Reached]:
        """Reach from `start`."""
        return await self.nodes.reach(
            start.id,
            relationship=relationship,
            direction=direction,  # type: ignore[arg-type]
            max_depth=depth,
            scope=scope,
        )


@pytest.fixture(
    params=["in_memory", pytest.param("postgres", marks=pytest.mark.integration)]
)
def store(request: pytest.FixtureRequest) -> Store:
    """The same scenarios run against both adapters."""
    if request.param == "in_memory":
        edge_store: dict[uuid.UUID, Edge] = {}
        return Store(
            InMemoryNodeRepository(edges=edge_store),
            InMemoryEdgeRepository(edge_store),
        )
    session = request.getfixturevalue("db_session")
    return Store(SqlAlchemyNodeRepository(session), SqlAlchemyEdgeRepository(session))


def _ids(found: list[Reached]) -> list[tuple[uuid.UUID, int]]:
    return [(r.node_id, r.depth) for r in found]


async def test_a_chain_is_followed_to_the_end(store: Store) -> None:
    """Box holds bag holds pouch: each is reached at its own depth."""
    box, bag, pouch = [await store.item(n) for n in ("box", "bag", "pouch")]
    await store.link(box, bag)
    await store.link(bag, pouch)

    found = await store.reach(box)

    assert _ids(found) == [(bag.id, 1), (pouch.id, 2)]


async def test_depth_stops_the_walk(store: Store) -> None:
    """A depth of one reaches only direct children."""
    box, bag, pouch = [await store.item(n) for n in ("box", "bag", "pouch")]
    await store.link(box, bag)
    await store.link(bag, pouch)

    assert _ids(await store.reach(box, depth=1)) == [(bag.id, 1)]


async def test_the_in_direction_finds_ancestors(store: Store) -> None:
    """Walking `in` from the pouch finds the bag, then the box."""
    box, bag, pouch = [await store.item(n) for n in ("box", "bag", "pouch")]
    await store.link(box, bag)
    await store.link(bag, pouch)

    found = await store.reach(pouch, direction="in")

    assert _ids(found) == [(bag.id, 1), (box.id, 2)]


async def test_a_loop_terminates_and_reports_each_item_once(store: Store) -> None:
    """A holds B holds A: B is reached once; the start is never reported."""
    a, b = await store.item("a"), await store.item("b")
    await store.link(a, b)
    await store.link(b, a)

    assert _ids(await store.reach(a)) == [(b.id, 1)]


async def test_a_diamond_reports_the_far_item_once_at_its_shallowest_depth(
    store: Store,
) -> None:
    """D is under both B and C but appears once, at depth two."""
    a, b, c, d = [await store.item(n) for n in "abcd"]
    for source, target in ((a, b), (a, c), (b, d), (c, d)):
        await store.link(source, target)

    found = await store.reach(a)

    assert sorted(_ids(found), key=lambda pair: (pair[1], pair[0])) == sorted(
        [(b.id, 1), (c.id, 1), (d.id, 2)], key=lambda pair: (pair[1], pair[0])
    )
    assert [r.depth for r in found] == [1, 1, 2]


async def test_other_relationships_are_ignored(store: Store) -> None:
    """Only the named relationship is followed."""
    a, b = await store.item("a"), await store.item("b")
    await store.link(a, b, type_slug="related-to")

    assert await store.reach(a) == []


async def test_a_deleted_intermediate_item_breaks_the_chain(store: Store) -> None:
    """Nothing beyond a deleted item is reached."""
    box = await store.item("box")
    bag = await store.item("bag", deleted=True)
    pouch = await store.item("pouch")
    await store.link(box, bag)
    await store.link(bag, pouch)

    assert await store.reach(box) == []


async def test_a_deleted_connection_breaks_the_chain(store: Store) -> None:
    """A deleted connection is not followed."""
    box, bag, pouch = [await store.item(n) for n in ("box", "bag", "pouch")]
    await store.link(box, bag)
    await store.link(bag, pouch, deleted=True)

    assert _ids(await store.reach(box)) == [(bag.id, 1)]


async def test_another_persons_intermediate_item_breaks_the_chain(
    store: Store,
) -> None:
    """Items and connections outside the scope are not walked through."""
    box = await store.item("box")
    theirs = await store.item("theirs", owner=BOB)
    pouch = await store.item("pouch")
    await store.link(box, theirs)
    await store.link(theirs, pouch)

    assert await store.reach(box) == []


async def test_another_persons_connection_breaks_the_chain(store: Store) -> None:
    """A connection owned by someone else is not followed."""
    box, bag, pouch = [await store.item(n) for n in ("box", "bag", "pouch")]
    await store.link(box, bag)
    await store.link(bag, pouch, owner=BOB)

    assert _ids(await store.reach(box)) == [(bag.id, 1)]


async def test_results_are_ordered_by_depth_then_id(store: Store) -> None:
    """Shallower items come first; ties fall back to id."""
    root = await store.item("root")
    kids = [await store.item(f"k{i}") for i in range(3)]
    grand = await store.item("grand")
    for kid in kids:
        await store.link(root, kid)
    await store.link(kids[0], grand)

    found = await store.reach(root)

    assert [r.depth for r in found] == [1, 1, 1, 2]
    assert [r.node_id for r in found[:3]] == sorted(k.id for k in kids)


async def test_a_long_chain_is_cut_at_the_depth_limit(store: Store) -> None:
    """A 30-link chain with a limit of 25 reaches 25 items among unrelated links."""
    chain = [await store.item(f"c{i}") for i in range(31)]
    for source, target in itertools.pairwise(chain):
        await store.link(source, target)
    for i in range(200):
        await store.link(await store.item(f"x{i}"), await store.item(f"y{i}"))

    found = await store.reach(chain[0], depth=25)

    assert [r.depth for r in found] == list(range(1, 26))
    assert found[-1].node_id == chain[25].id
