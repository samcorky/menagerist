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
from app.modules.graph.application.list_node_types import (
    ListNodeTypes,
    ListNodeTypesQuery,
)
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.actor import SYSTEM_ACTOR


def _make_repos(node_types: InMemoryNodeTypeRepository) -> GraphRepos:
    return GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=node_types,
        edge_types=InMemoryEdgeTypeRepository(),
    )


async def test_list_node_types_returns_all() -> None:
    """ListNodeTypes returns all non-deleted node types."""
    node_types = InMemoryNodeTypeRepository()
    film = NodeType.create(slug="film", label="Film")
    book = NodeType.create(slug="book", label="Book")
    await node_types.add(film)
    await node_types.add(book)
    use_case = ListNodeTypes(_make_repos(node_types))

    results = await use_case.handle(ListNodeTypesQuery(), SYSTEM_ACTOR)

    assert film in results
    assert book in results


async def test_list_node_types_respects_limit() -> None:
    """ListNodeTypes returns at most `limit` items."""
    node_types = InMemoryNodeTypeRepository()
    for i in range(5):
        await node_types.add(NodeType.create(slug=f"type-{i}", label=f"Type {i}"))
    use_case = ListNodeTypes(_make_repos(node_types))

    results = await use_case.handle(ListNodeTypesQuery(limit=3), SYSTEM_ACTOR)

    assert len(results) <= 3


async def test_list_node_types_excludes_deleted() -> None:
    """ListNodeTypes omits soft-deleted node types."""
    node_types = InMemoryNodeTypeRepository()
    nt = NodeType.create(slug="film", label="Film")
    nt.soft_delete()
    await node_types.add(nt)
    use_case = ListNodeTypes(_make_repos(node_types))

    results = await use_case.handle(ListNodeTypesQuery(), SYSTEM_ACTOR)

    assert nt not in results


async def test_list_node_types_fills_in_linked_choice_options() -> None:
    """Listing returns linked choice fields with their list's options filled in."""
    schema = {
        "type": "object",
        "properties": {
            "condition": {
                "type": "string",
                "x-menagerist": {
                    "kind": "choice",
                    "list": "6f1d2a7e-3c4b-4e5f-8a9b-0c1d2e3f4a5b",
                },
            }
        },
    }
    node_types = InMemoryNodeTypeRepository()
    film = NodeType.create(slug="film", label="Film", attributes_schema=schema)
    await node_types.add(film)

    class _Options:
        async def options(self, list_id: str) -> list[str]:
            """Return fixed options."""
            return ["Mint"]

    results = await ListNodeTypes(_make_repos(node_types), _Options()).handle(
        ListNodeTypesQuery(), SYSTEM_ACTOR
    )

    assert results[0].attributes_schema is not None
    assert results[0].attributes_schema["properties"]["condition"]["enum"] == ["Mint"]
