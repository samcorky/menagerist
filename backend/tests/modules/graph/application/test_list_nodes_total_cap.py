"""ListNodes: a text search's total stops at the cap; other lists count exactly."""

import uuid

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
from app.modules.graph.application.search_nodes import TOTAL_CAP
from app.modules.graph.domain.node import Node
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR

OWNER = uuid.UUID(int=1)


async def _use_case(count: int, total_cap: int = TOTAL_CAP) -> ListNodes:
    nodes = InMemoryNodeRepository()
    for i in range(count):
        await nodes.add(Node.create(owner_id=OWNER, name=f"Coin {i}", type="coin"))
    repos = GraphRepos(
        nodes=nodes,
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )
    return ListNodes(repos, InMemoryAccessGuard(), total_cap=total_cap)


async def test_search_over_the_default_cap_is_capped() -> None:
    """1,005 matches report 1,000 and say so; the page is still full."""
    use_case = await _use_case(TOTAL_CAP + 5)

    result = await use_case.handle(ListNodesQuery(q="coin", limit=10), SYSTEM_ACTOR)

    assert (result.total, result.total_capped) == (TOTAL_CAP, True)
    assert len(result.items) == 10


async def test_search_at_the_cap_is_exact() -> None:
    """Exactly the cap is not 'more than the cap'."""
    use_case = await _use_case(3, total_cap=3)

    result = await use_case.handle(ListNodesQuery(q="coin"), SYSTEM_ACTOR)

    assert (result.total, result.total_capped) == (3, False)


async def test_search_under_the_cap_is_exact() -> None:
    """Fewer matches than the cap are counted exactly, with no flag."""
    use_case = await _use_case(5, total_cap=10)

    result = await use_case.handle(ListNodesQuery(q="coin"), SYSTEM_ACTOR)

    assert (result.total, result.total_capped) == (5, False)


async def test_capped_search_still_pages_in_id_order() -> None:
    """Capping the count leaves the items and keyset paging alone."""
    use_case = await _use_case(6, total_cap=2)

    first = await use_case.handle(ListNodesQuery(q="coin", limit=3), SYSTEM_ACTOR)
    second = await use_case.handle(
        ListNodesQuery(q="coin", limit=3, after=first.items[2].id), SYSTEM_ACTOR
    )

    ids = [n.id for n in first.items + second.items]
    assert ids == sorted(ids)
    assert len(set(ids)) == 6
    assert first.total == second.total == 2


async def test_list_without_search_is_never_capped() -> None:
    """Plain lists keep an exact count, whatever the cap."""
    use_case = await _use_case(5, total_cap=2)

    result = await use_case.handle(ListNodesQuery(type="coin"), SYSTEM_ACTOR)

    assert (result.total, result.total_capped) == (5, False)
