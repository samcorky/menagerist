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
from app.modules.graph.application.list_nodes import ListNodes, ListNodesQuery
from app.modules.graph.domain.node import Node
from app.modules.graph.ports.unit_of_work import GraphRepos, GraphUnitOfWork
from app.shared_kernel.actor import SYSTEM_ACTOR


def _make_uow(nodes: InMemoryNodeRepository) -> GraphUnitOfWork:
    return create_in_memory_graph_uow(
        GraphRepos(
            nodes=nodes,
            edges=InMemoryEdgeRepository(),
            node_types=InMemoryNodeTypeRepository(),
            edge_types=InMemoryEdgeTypeRepository(),
        )
    )


async def test_list_nodes_filters_by_type() -> None:
    """ListNodes returns only nodes matching the requested type."""
    nodes = InMemoryNodeRepository()
    film = Node.create(name="Alien", type="film")
    person = Node.create(name="Ridley Scott", type="person")
    await nodes.add(film)
    await nodes.add(person)
    use_case = ListNodes(_make_uow(nodes))

    result = await use_case.handle(ListNodesQuery(type="film"), SYSTEM_ACTOR)

    assert result.items == [film]
    assert person not in result.items


async def test_list_nodes_filters_by_search_query() -> None:
    """ListNodes passes q to the repository and returns only matching nodes."""
    nodes = InMemoryNodeRepository()
    alien = Node.create(name="Alien", type="film")
    predator = Node.create(name="Predator", type="film")
    await nodes.add(alien)
    await nodes.add(predator)
    use_case = ListNodes(_make_uow(nodes))

    result = await use_case.handle(ListNodesQuery(q="alien"), SYSTEM_ACTOR)

    assert result.items == [alien]
    assert predator not in result.items


async def test_list_nodes_orders_by_id_and_paginates() -> None:
    """ListNodes returns node ordered by id, respecting after/limit."""
    nodes = InMemoryNodeRepository()
    node_list = [Node.create(name="Alien", type="film") for _ in range(3)]
    for node in node_list:
        await nodes.add(node)
    expected_order = sorted(node_list, key=lambda n: n.id)
    uow = _make_uow(nodes)
    use_case = ListNodes(uow)

    first_page = await use_case.handle(
        ListNodesQuery(after=None, limit=2), SYSTEM_ACTOR
    )

    assert first_page.items == expected_order[:2]

    second_page = await use_case.handle(
        ListNodesQuery(after=first_page.items[-1].id, limit=2), SYSTEM_ACTOR
    )

    assert second_page.items == expected_order[2:]


async def test_list_nodes_total_reflects_all_matching_nodes() -> None:
    """ListNodes.total counts all matches regardless of pagination limit."""
    nodes = InMemoryNodeRepository()
    for _ in range(5):
        await nodes.add(Node.create(name="Alien", type="film"))
    use_case = ListNodes(_make_uow(nodes))

    result = await use_case.handle(ListNodesQuery(limit=2), SYSTEM_ACTOR)

    assert len(result.items) == 2
    assert result.total == 5
