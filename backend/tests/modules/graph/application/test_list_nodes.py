from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.application.list_nodes import ListNodes, ListNodesQuery
from app.modules.graph.domain.node import Node
from app.shared_kernel.actor import SYSTEM_ACTOR


async def test_list_nodes_orders_by_id_and_paginates() -> None:
    """ListNodes returns node ordered by id, respecting after/limit."""
    repository = InMemoryNodeRepository()
    nodes = [Node.create(name="Alien", type="film") for _ in range(3)]
    for node in nodes:
        await repository.add(node)
    expected_order = sorted(nodes, key=lambda node: node.id)
    use_case = ListNodes(repository)

    first_page = await use_case.handle(
        ListNodesQuery(after=None, limit=2), SYSTEM_ACTOR
    )

    assert first_page == expected_order[:2]

    second_page = await use_case.handle(
        ListNodesQuery(after=first_page[-1].id, limit=2), SYSTEM_ACTOR
    )

    assert second_page == expected_order[2:]
