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
from app.modules.graph.application.update_edge_type import (
    UpdateEdgeType,
    UpdateEdgeTypeCommand,
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


async def test_update_edge_type_persists_and_commits() -> None:
    """UpdateEdgeType saves the changed edge type and commits."""
    uow, repos = _make_uow()
    et = EdgeType.create(slug="directed-by", label="Directed By")
    await repos.edge_types.add(et)
    use_case = UpdateEdgeType(uow)

    result = await use_case.handle(
        UpdateEdgeTypeCommand(edge_type_id=et.id, label="Helmed By"),
        SYSTEM_ACTOR,
    )

    assert result.label == "Helmed By"
    stored = await repos.edge_types.get(et.id)
    assert stored is not None
    assert stored.label == "Helmed By"
    assert uow.committed is True


async def test_update_edge_type_persists_attributes_schema() -> None:
    """UpdateEdgeType stores attributes_schema when provided."""
    uow, repos = _make_uow()
    et = EdgeType.create(slug="directed-by", label="Directed By")
    await repos.edge_types.add(et)
    schema = {
        "fields": [
            {"key": "since", "label": "Since", "type": "date", "required": False}
        ]
    }
    use_case = UpdateEdgeType(uow)

    result = await use_case.handle(
        UpdateEdgeTypeCommand(edge_type_id=et.id, attributes_schema=schema),
        SYSTEM_ACTOR,
    )

    assert result.attributes_schema == schema
    stored = await repos.edge_types.get(et.id)
    assert stored is not None
    assert stored.attributes_schema == schema


async def test_update_edge_type_raises_when_missing() -> None:
    """UpdateEdgeType raises EdgeTypeNotFoundError when the edge type doesn't exist."""
    uow, _ = _make_uow()
    use_case = UpdateEdgeType(uow)

    with pytest.raises(EdgeTypeNotFoundError):
        await use_case.handle(
            UpdateEdgeTypeCommand(edge_type_id=uuid.uuid4(), label="Ghost"),
            SYSTEM_ACTOR,
        )
