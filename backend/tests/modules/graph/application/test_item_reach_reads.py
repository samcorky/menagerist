"""`ListItemContents` and `GetItemPath` over the in-memory repositories."""

import uuid

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
from app.modules.graph.application.get_item_path import GetItemPath, GetItemPathQuery
from app.modules.graph.application.list_item_contents import (
    ListItemContents,
    ListItemContentsQuery,
)
from app.modules.graph.domain.edge import Edge
from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.domain.errors import (
    EdgeTypeNotFoundError,
    NodeNotFoundError,
    RelationshipNotDirectionalError,
)
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.reach import InvalidReachDepthError
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR

OWNER = uuid.UUID(int=1)


class World:
    """A small store with helpers for building a box-in-box graph."""

    def __init__(self) -> None:
        edges: dict[uuid.UUID, Edge] = {}
        self.edges = InMemoryEdgeRepository(edges)
        self.nodes = InMemoryNodeRepository(edges=edges)
        self.types = InMemoryEdgeTypeRepository()
        self.repos = GraphRepos(
            nodes=self.nodes,
            edges=self.edges,
            node_types=InMemoryNodeTypeRepository(),
            edge_types=self.types,
        )
        self.contents = ListItemContents(self.repos, InMemoryAccessGuard())
        self.path = GetItemPath(self.repos, InMemoryAccessGuard())

    async def relationship(
        self, slug: str = "contains", *, directional: bool = True
    ) -> None:
        """Add a relationship type."""
        await self.types.add(
            EdgeType.create(
                owner_id=OWNER, slug=slug, label=slug, directional=directional
            )
        )

    async def item(self, name: str) -> Node:
        """Add an item."""
        node = Node.create(owner_id=OWNER, name=name, type=None)
        await self.nodes.add(node)
        return node

    async def hold(self, outer: Node, inner: Node, slug: str = "contains") -> None:
        """Make `outer` hold `inner`."""
        await self.edges.add(
            Edge.create(
                owner_id=OWNER, source_id=outer.id, target_id=inner.id, type=slug
            )
        )


async def _nested() -> tuple[World, Node, Node, Node]:
    world = World()
    await world.relationship()
    shed, box, bag = [await world.item(n) for n in ("shed", "box", "bag")]
    await world.hold(shed, box)
    await world.hold(box, bag)
    return world, shed, box, bag


async def test_contents_lists_nearest_first_with_depth() -> None:
    """The shed holds the box directly and the bag through it."""
    world, shed, box, bag = await _nested()

    found = await world.contents.handle(
        ListItemContentsQuery(item_id=shed.id, relationship="contains", depth=3),
        SYSTEM_ACTOR,
    )

    assert [(e.node.id, e.depth) for e in found] == [(box.id, 1), (bag.id, 2)]


async def test_contents_defaults_to_direct_children() -> None:
    """Without a depth only what the item holds directly is listed."""
    world, shed, box, _ = await _nested()

    found = await world.contents.handle(
        ListItemContentsQuery(item_id=shed.id, relationship="contains"), SYSTEM_ACTOR
    )

    assert [e.node.id for e in found] == [box.id]


async def test_contents_pages_with_after_and_limit() -> None:
    """The cursor is the last item of the previous page."""
    world, shed, box, bag = await _nested()
    query = ListItemContentsQuery(
        item_id=shed.id, relationship="contains", depth=3, limit=1
    )

    first = await world.contents.handle(query, SYSTEM_ACTOR)
    query.after = first[0].node.id
    second = await world.contents.handle(query, SYSTEM_ACTOR)
    query.after = second[0].node.id
    third = await world.contents.handle(query, SYSTEM_ACTOR)

    assert [first[0].node.id, second[0].node.id, third] == [box.id, bag.id, []]


async def test_contents_after_an_unknown_item_is_an_empty_page() -> None:
    """A cursor that is no longer in the contents ends the listing."""
    world, shed, _, _ = await _nested()

    found = await world.contents.handle(
        ListItemContentsQuery(
            item_id=shed.id, relationship="contains", depth=3, after=uuid.uuid4()
        ),
        SYSTEM_ACTOR,
    )

    assert found == []


async def test_path_is_outermost_first() -> None:
    """The bag sits in the box in the shed: shed, then box."""
    world, shed, box, bag = await _nested()

    found = await world.path.handle(
        GetItemPathQuery(item_id=bag.id, relationship="contains"), SYSTEM_ACTOR
    )

    assert [n.id for n in found] == [shed.id, box.id]


async def test_path_depth_limits_how_far_up() -> None:
    """A depth of one gives only the direct holder."""
    world, _, box, bag = await _nested()

    found = await world.path.handle(
        GetItemPathQuery(item_id=bag.id, relationship="contains", depth=1), SYSTEM_ACTOR
    )

    assert [n.id for n in found] == [box.id]


async def test_an_item_that_is_missing_is_not_found() -> None:
    """Both reads refuse an item the caller cannot see."""
    world = World()
    await world.relationship()

    with pytest.raises(NodeNotFoundError):
        await world.contents.handle(
            ListItemContentsQuery(item_id=uuid.uuid4(), relationship="contains"),
            SYSTEM_ACTOR,
        )
    with pytest.raises(NodeNotFoundError):
        await world.path.handle(
            GetItemPathQuery(item_id=uuid.uuid4(), relationship="contains"),
            SYSTEM_ACTOR,
        )


async def test_an_unknown_relationship_is_not_found() -> None:
    """The relationship slug must name a live relationship type."""
    world = World()
    item = await world.item("box")

    with pytest.raises(EdgeTypeNotFoundError):
        await world.contents.handle(
            ListItemContentsQuery(item_id=item.id, relationship="nope"), SYSTEM_ACTOR
        )


async def test_a_relationship_without_direction_is_refused() -> None:
    """Contents and path mean nothing without an inside and an outside."""
    world = World()
    await world.relationship("sibling", directional=False)
    item = await world.item("box")

    with pytest.raises(RelationshipNotDirectionalError):
        await world.path.handle(
            GetItemPathQuery(item_id=item.id, relationship="sibling"), SYSTEM_ACTOR
        )


@pytest.mark.parametrize("depth", [0, 26])
async def test_a_depth_out_of_range_is_refused(depth: int) -> None:
    """The depth is 1 to 25."""
    world = World()
    await world.relationship()
    item = await world.item("box")

    with pytest.raises(InvalidReachDepthError):
        await world.contents.handle(
            ListItemContentsQuery(
                item_id=item.id, relationship="contains", depth=depth
            ),
            SYSTEM_ACTOR,
        )
