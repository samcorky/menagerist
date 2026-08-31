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
from app.modules.graph.application.update_node_type import (
    UpdateNodeType,
    UpdateNodeTypeCommand,
)
from app.modules.graph.domain.errors import NodeTypeNotFoundError
from app.modules.graph.domain.node_type import NodeType
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


async def test_update_node_type_persists_and_commits() -> None:
    """UpdateNodeType saves the changed node type and commits."""
    uow, repos = _make_uow()
    nt = NodeType.create(slug="film", label="Film")
    await repos.node_types.add(nt)
    use_case = UpdateNodeType(uow)

    result = await use_case.handle(
        UpdateNodeTypeCommand(node_type_id=nt.id, label="Movie"),
        SYSTEM_ACTOR,
    )

    assert result.label == "Movie"
    stored = await repos.node_types.get(nt.id)
    assert stored is not None
    assert stored.label == "Movie"
    assert uow.committed is True


async def test_update_node_type_persists_attributes_schema() -> None:
    """UpdateNodeType stores attributes_schema when provided."""
    uow, repos = _make_uow()
    nt = NodeType.create(slug="film", label="Film")
    await repos.node_types.add(nt)
    schema = {
        "fields": [
            {"key": "year", "label": "Year", "type": "number", "required": False}
        ]
    }
    use_case = UpdateNodeType(uow)

    result = await use_case.handle(
        UpdateNodeTypeCommand(node_type_id=nt.id, attributes_schema=schema),
        SYSTEM_ACTOR,
    )

    assert result.attributes_schema == schema
    stored = await repos.node_types.get(nt.id)
    assert stored is not None
    assert stored.attributes_schema == schema


async def test_update_node_type_raises_when_missing() -> None:
    """UpdateNodeType raises NodeTypeNotFoundError when the node type doesn't exist."""
    uow, _ = _make_uow()
    use_case = UpdateNodeType(uow)

    with pytest.raises(NodeTypeNotFoundError):
        await use_case.handle(
            UpdateNodeTypeCommand(node_type_id=uuid.uuid4(), label="Ghost"),
            SYSTEM_ACTOR,
        )
