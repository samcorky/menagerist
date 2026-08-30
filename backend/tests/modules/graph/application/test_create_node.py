from app.modules.graph.adapters.persistence.in_memory_edge_repository import (
    InMemoryEdgeRepository,
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
from app.modules.graph.application.create_node import CreateNode, CreateNodeCommand
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.actor import SYSTEM_ACTOR


async def test_create_node_persists_and_commits() -> None:
    """CreateNode adds the node to the repository and commits the unit of work."""
    repos = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
    )
    uow = create_in_memory_graph_uow(repos)
    use_case = CreateNode(uow)

    node = await use_case.handle(
        CreateNodeCommand(name="Alien", type="film", attributes={"title": "Alien"}),
        SYSTEM_ACTOR,
    )

    assert await repos.nodes.get(node.id) is node
    assert uow.committed is True
