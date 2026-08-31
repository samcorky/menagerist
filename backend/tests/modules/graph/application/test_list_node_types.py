from app.modules.graph.adapters.persistence.in_memory_node_type_repository import (
    InMemoryNodeTypeRepository,
)
from app.modules.graph.application.list_node_types import (
    ListNodeTypes,
    ListNodeTypesQuery,
)
from app.modules.graph.domain.node_type import NodeType
from app.shared_kernel.actor import SYSTEM_ACTOR


async def test_list_node_types_returns_all() -> None:
    """ListNodeTypes returns all non-deleted node types."""
    repo = InMemoryNodeTypeRepository()
    film = NodeType.create(slug="film", label="Film")
    book = NodeType.create(slug="book", label="Book")
    await repo.add(film)
    await repo.add(book)
    use_case = ListNodeTypes(repo)

    results = await use_case.handle(ListNodeTypesQuery(), SYSTEM_ACTOR)

    assert film in results
    assert book in results


async def test_list_node_types_respects_limit() -> None:
    """ListNodeTypes returns at most `limit` items."""
    repo = InMemoryNodeTypeRepository()
    for i in range(5):
        await repo.add(NodeType.create(slug=f"type-{i}", label=f"Type {i}"))
    use_case = ListNodeTypes(repo)

    results = await use_case.handle(ListNodeTypesQuery(limit=3), SYSTEM_ACTOR)

    assert len(results) <= 3


async def test_list_node_types_excludes_deleted() -> None:
    """ListNodeTypes omits soft-deleted node types."""
    repo = InMemoryNodeTypeRepository()
    nt = NodeType.create(slug="film", label="Film")
    nt.soft_delete()
    await repo.add(nt)
    use_case = ListNodeTypes(repo)

    results = await use_case.handle(ListNodeTypesQuery(), SYSTEM_ACTOR)

    assert nt not in results
