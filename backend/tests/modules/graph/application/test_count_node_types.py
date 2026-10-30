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
from app.modules.graph.application.count_node_types import (
    CountNodeTypes,
    CountNodeTypesQuery,
)
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.query import TypeCount
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import Actor

ALICE = Actor(id=uuid.UUID(int=11), roles=frozenset({"member"}))
BOB = Actor(id=uuid.UUID(int=12), roles=frozenset({"member"}))


def _repos() -> GraphRepos:
    return GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )


async def test_returns_nothing_when_there_are_no_items() -> None:
    """Returns nothing when there are no items."""
    result = await CountNodeTypes(_repos(), InMemoryAccessGuard()).handle(
        CountNodeTypesQuery(), ALICE
    )

    assert result == []


async def test_counts_each_type_for_the_actors_own_items_only() -> None:
    """Counts each type for the actors own items only."""
    repos = _repos()
    for owner, slug in (
        (ALICE.id, "film"),
        (ALICE.id, "film"),
        (ALICE.id, None),
        (BOB.id, "book"),
        (BOB.id, "film"),
    ):
        await repos.nodes.add(Node.create(owner_id=owner, name="n", type=slug))

    mine = await CountNodeTypes(repos, InMemoryAccessGuard()).handle(
        CountNodeTypesQuery(), ALICE
    )
    theirs = await CountNodeTypes(repos, InMemoryAccessGuard()).handle(
        CountNodeTypesQuery(), BOB
    )

    assert mine == [TypeCount(type="film", count=2), TypeCount(type=None, count=1)]
    assert theirs == [TypeCount(type="book", count=1), TypeCount(type="film", count=1)]
