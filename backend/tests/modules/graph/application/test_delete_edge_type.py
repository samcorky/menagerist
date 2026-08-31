import uuid

import pytest

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
from app.modules.graph.application.delete_edge_type import (
    DeleteEdgeType,
    DeleteEdgeTypeCommand,
)
from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.domain.errors import EdgeTypeNotFoundError
from app.modules.graph.ports.unit_of_work import GraphRepos, GraphUnitOfWork
from app.shared_kernel.actor import SYSTEM_ACTOR


def _make_uow() -> tuple[GraphUnitOfWork, GraphRepos]:
    repos = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )
    return create_in_memory_graph_uow(repos), repos


async def test_delete_edge_type_soft_deletes_and_commits() -> None:
    """DeleteEdgeType marks the edge type as deleted and commits."""
    uow, repos = _make_uow()
    et = EdgeType.create(slug="directed-by", label="Directed By")
    await repos.edge_types.add(et)
    use_case = DeleteEdgeType(uow)

    await use_case.handle(DeleteEdgeTypeCommand(edge_type_id=et.id), SYSTEM_ACTOR)

    assert et.is_deleted is True
    assert uow.committed is True


async def test_delete_edge_type_raises_when_missing() -> None:
    """DeleteEdgeType raises EdgeTypeNotFoundError when the edge type doesn't exist."""
    uow, _ = _make_uow()
    use_case = DeleteEdgeType(uow)

    with pytest.raises(EdgeTypeNotFoundError):
        await use_case.handle(
            DeleteEdgeTypeCommand(edge_type_id=uuid.uuid4()), SYSTEM_ACTOR
        )
