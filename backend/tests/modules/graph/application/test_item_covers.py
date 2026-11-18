"""ListNodes and SearchNodes hand back each listed item's cover thumbnail."""

import uuid
from datetime import date

from app.modules.graph.adapters.persistence.in_memory_edge_repository import (
    InMemoryEdgeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_edge_type_repository import (
    InMemoryEdgeTypeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_item_covers import (
    InMemoryItemCovers,
)
from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_node_type_repository import (
    InMemoryNodeTypeRepository,
)
from app.modules.graph.application.list_nodes import ListNodes, ListNodesQuery
from app.modules.graph.application.search_nodes import SearchNodes, SearchNodesQuery
from app.modules.graph.domain.node import Node
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR

_OWNER = uuid.UUID(int=1)


async def _world() -> tuple[GraphRepos, Node, Node, InMemoryItemCovers]:
    repos = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )
    with_cover = Node.create(owner_id=_OWNER, name="Alien")
    bare = Node.create(owner_id=_OWNER, name="Aliens")
    await repos.nodes.add(with_cover)
    await repos.nodes.add(bare)
    covers = InMemoryItemCovers()
    covers.set(with_cover.id, "/api/v1/media/abc/thumbnail")
    covers.set(uuid.uuid4(), "/api/v1/media/other/thumbnail")
    return repos, with_cover, bare, covers


async def test_a_list_carries_the_cover_of_each_item_that_has_one() -> None:
    """Only listed items with a cover appear, keyed by the item."""
    repos, with_cover, _, covers = await _world()
    use_case = ListNodes(repos, InMemoryAccessGuard(), item_covers=covers)

    result = await use_case.handle(ListNodesQuery(), SYSTEM_ACTOR)

    assert result.covers == {with_cover.id: "/api/v1/media/abc/thumbnail"}


async def test_a_list_without_a_cover_source_has_no_covers() -> None:
    """Without the port wired, the list is as it was."""
    repos, _, _, _ = await _world()

    result = await ListNodes(repos, InMemoryAccessGuard()).handle(
        ListNodesQuery(), SYSTEM_ACTOR
    )

    assert result.covers == {}


async def test_an_empty_list_asks_for_no_covers() -> None:
    """A page with no items does not call the source."""
    repos, _, _, covers = await _world()
    use_case = ListNodes(repos, InMemoryAccessGuard(), item_covers=covers)

    await use_case.handle(ListNodesQuery(q="no such item"), SYSTEM_ACTOR)

    assert covers.asked == []


async def test_a_search_carries_the_cover_of_each_item_that_has_one() -> None:
    """A search page gets its covers the same way."""
    repos, with_cover, _, covers = await _world()
    use_case = SearchNodes(
        repos,
        InMemoryAccessGuard(),
        today=lambda: date(2026, 10, 14),
        item_covers=covers,
    )

    result = await use_case.handle(
        SearchNodesQuery(query={"v": 1, "where": None}, limit=10), SYSTEM_ACTOR
    )

    assert result.covers == {with_cover.id: "/api/v1/media/abc/thumbnail"}
