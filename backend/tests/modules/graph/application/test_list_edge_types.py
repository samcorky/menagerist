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
from app.modules.graph.adapters.persistence.unit_of_work import (
    create_in_memory_graph_uow,
)
from app.modules.graph.application.list_edge_types import (
    ListEdgeTypes,
    ListEdgeTypesQuery,
)
from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.ports.unit_of_work import GraphRepos, GraphUnitOfWork
from app.shared_kernel.actor import SYSTEM_ACTOR


def _make_uow(edge_types: InMemoryEdgeTypeRepository) -> GraphUnitOfWork:
    return create_in_memory_graph_uow(
        GraphRepos(
            nodes=InMemoryNodeRepository(),
            edges=InMemoryEdgeRepository(),
            node_types=InMemoryNodeTypeRepository(),
            edge_types=edge_types,
        )
    )


async def test_list_edge_types_returns_all() -> None:
    """ListEdgeTypes returns all non-deleted edge types."""
    edge_types = InMemoryEdgeTypeRepository()
    et1 = EdgeType.create(slug="directed-by", label="Directed By")
    et2 = EdgeType.create(slug="written-by", label="Written By")
    await edge_types.add(et1)
    await edge_types.add(et2)
    use_case = ListEdgeTypes(_make_uow(edge_types))

    results = await use_case.handle(ListEdgeTypesQuery(), SYSTEM_ACTOR)

    assert et1 in results
    assert et2 in results


async def test_list_edge_types_respects_limit() -> None:
    """ListEdgeTypes returns at most `limit` items."""
    edge_types = InMemoryEdgeTypeRepository()
    for i in range(5):
        await edge_types.add(EdgeType.create(slug=f"type-{i}", label=f"Type {i}"))
    use_case = ListEdgeTypes(_make_uow(edge_types))

    results = await use_case.handle(ListEdgeTypesQuery(limit=2), SYSTEM_ACTOR)

    assert len(results) <= 2


async def test_list_edge_types_excludes_deleted() -> None:
    """ListEdgeTypes omits soft-deleted edge types."""
    edge_types = InMemoryEdgeTypeRepository()
    et = EdgeType.create(slug="directed-by", label="Directed By")
    et.soft_delete()
    await edge_types.add(et)
    use_case = ListEdgeTypes(_make_uow(edge_types))

    results = await use_case.handle(ListEdgeTypesQuery(), SYSTEM_ACTOR)

    assert et not in results
