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
from app.modules.graph.adapters.persistence.unit_of_work import (
    create_in_memory_graph_uow,
)
from app.modules.graph.application.claim_orphaned_items import (
    ClaimOrphanedItems,
    ClaimOrphanedItemsCommand,
)
from app.modules.graph.domain.edge import Edge
from app.modules.graph.domain.node import Node
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.actor import SYSTEM_ACTOR


async def test_claims_system_owned_items_and_connections_and_commits() -> None:
    """System-owned content moves to the new owner; the unit of work commits."""
    nodes = InMemoryNodeRepository()
    edges = InMemoryEdgeRepository()
    uow = create_in_memory_graph_uow(
        GraphRepos(
            nodes=nodes,
            edges=edges,
            node_types=InMemoryNodeTypeRepository(),
            edge_types=InMemoryEdgeTypeRepository(),
        )
    )
    node = Node.create(owner_id=SYSTEM_ACTOR.id, name="n")
    other = Node.create(owner_id=uuid.uuid7(), name="o")
    edge = Edge.create(
        owner_id=SYSTEM_ACTOR.id, source_id=node.id, target_id=other.id, type="t"
    )
    for n in (node, other):
        await nodes.add(n)
    await edges.add(edge)
    owner = uuid.uuid7()

    result = await ClaimOrphanedItems(uow).handle(
        ClaimOrphanedItemsCommand(owner_id=owner), SYSTEM_ACTOR
    )

    assert (result.items, result.connections) == (1, 1)
    assert node.owner_id == edge.owner_id == owner
    assert other.owner_id != owner
    assert getattr(uow, "committed", False)
