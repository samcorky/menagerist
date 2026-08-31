from app.modules.graph.adapters.persistence.in_memory_edge_type_repository import (
    InMemoryEdgeTypeRepository,
)
from app.modules.graph.application.list_edge_types import (
    ListEdgeTypes,
    ListEdgeTypesQuery,
)
from app.modules.graph.domain.edge_type import EdgeType
from app.shared_kernel.actor import SYSTEM_ACTOR


async def test_list_edge_types_returns_all() -> None:
    """ListEdgeTypes returns all non-deleted edge types."""
    repo = InMemoryEdgeTypeRepository()
    et1 = EdgeType.create(slug="directed-by", label="Directed By")
    et2 = EdgeType.create(slug="written-by", label="Written By")
    await repo.add(et1)
    await repo.add(et2)
    use_case = ListEdgeTypes(repo)

    results = await use_case.handle(ListEdgeTypesQuery(), SYSTEM_ACTOR)

    assert et1 in results
    assert et2 in results


async def test_list_edge_types_respects_limit() -> None:
    """ListEdgeTypes returns at most `limit` items."""
    repo = InMemoryEdgeTypeRepository()
    for i in range(5):
        await repo.add(EdgeType.create(slug=f"type-{i}", label=f"Type {i}"))
    use_case = ListEdgeTypes(repo)

    results = await use_case.handle(ListEdgeTypesQuery(limit=2), SYSTEM_ACTOR)

    assert len(results) <= 2


async def test_list_edge_types_excludes_deleted() -> None:
    """ListEdgeTypes omits soft-deleted edge types."""
    repo = InMemoryEdgeTypeRepository()
    et = EdgeType.create(slug="directed-by", label="Directed By")
    et.soft_delete()
    await repo.add(et)
    use_case = ListEdgeTypes(repo)

    results = await use_case.handle(ListEdgeTypesQuery(), SYSTEM_ACTOR)

    assert et not in results
