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
from app.modules.graph.application.claim_orphaned_types import (
    ClaimOrphanedTypes,
    ClaimOrphanedTypesCommand,
)
from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR


async def test_claims_system_owned_and_ownerless_types_and_commits() -> None:
    """Legacy types of both kinds move to the new owner; owned ones stay put."""
    node_types = InMemoryNodeTypeRepository()
    edge_types = InMemoryEdgeTypeRepository()
    uow = create_in_memory_graph_uow(
        GraphRepos(
            nodes=InMemoryNodeRepository(),
            edges=InMemoryEdgeRepository(),
            node_types=node_types,
            edge_types=edge_types,
        )
    )
    legacy = NodeType.create(owner_id=SYSTEM_ACTOR.id, slug="book", label="Book")
    ownerless = NodeType.create(owner_id=SYSTEM_ACTOR.id, slug="film", label="Film")
    ownerless.owner_id = None
    theirs = NodeType.create(owner_id=uuid.uuid7(), slug="game", label="Game")
    edge = EdgeType.create(owner_id=SYSTEM_ACTOR.id, slug="by", label="By")
    for node_type in (legacy, ownerless, theirs):
        await node_types.add(node_type)
    await edge_types.add(edge)
    owner = uuid.uuid7()

    result = await ClaimOrphanedTypes(uow, InMemoryAccessGuard()).handle(
        ClaimOrphanedTypesCommand(owner_id=owner), SYSTEM_ACTOR
    )

    assert (result.item_types, result.relationship_types) == (2, 1)
    assert legacy.owner_id == ownerless.owner_id == edge.owner_id == owner
    assert theirs.owner_id != owner
    assert getattr(uow, "committed", False)
