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
from app.modules.graph.application.type_catalogue import (
    load_edge_types,
    load_node_types,
)
from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.content_filter import ContentFilter


def _repos(node_types: InMemoryNodeTypeRepository) -> GraphRepos:
    return GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=node_types,
        edge_types=InMemoryEdgeTypeRepository(),
    )


async def test_loads_every_type_across_several_pages() -> None:
    """Every type is returned when the catalogue spans pages."""
    node_types = InMemoryNodeTypeRepository()
    for i in range(250):
        await node_types.add(
            NodeType.create(
                owner_id=SYSTEM_ACTOR.id, slug=f"type-{i}", label=f"Type {i}"
            )
        )

    loaded = await load_node_types(_repos(node_types), ContentFilter.everyone())

    assert len(loaded) == 250
    assert len({t.id for t in loaded}) == 250


async def test_loads_an_exact_page_multiple() -> None:
    """An exact page multiple ends on the empty trailing page."""
    node_types = InMemoryNodeTypeRepository()
    for i in range(200):
        await node_types.add(
            NodeType.create(
                owner_id=SYSTEM_ACTOR.id, slug=f"type-{i}", label=f"Type {i}"
            )
        )

    assert (
        len(await load_node_types(_repos(node_types), ContentFilter.everyone())) == 200
    )


async def test_loads_nothing_when_there_are_no_types() -> None:
    """An empty catalogue yields an empty list."""
    assert (
        await load_node_types(
            _repos(InMemoryNodeTypeRepository()), ContentFilter.everyone()
        )
        == []
    )


async def test_loads_every_relationship_type_across_several_pages() -> None:
    """Relationship types are read a page at a time, and none is skipped."""
    edge_types = InMemoryEdgeTypeRepository()
    for i in range(250):
        await edge_types.add(
            EdgeType.create(owner_id=SYSTEM_ACTOR.id, slug=f"rel-{i}", label=f"Rel {i}")
        )
    repos = _repos(InMemoryNodeTypeRepository())
    repos.edge_types = edge_types

    loaded = await load_edge_types(repos, ContentFilter.everyone())

    assert len({t.id for t in loaded}) == 250
    assert (
        await load_edge_types(
            _repos(InMemoryNodeTypeRepository()), ContentFilter.everyone()
        )
        == []
    )
