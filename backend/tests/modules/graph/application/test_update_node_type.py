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
from app.modules.graph.application.update_node_type import (
    UpdateNodeType,
    UpdateNodeTypeCommand,
)
from app.modules.graph.domain.errors import InvalidSchemaError, NodeTypeNotFoundError
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork


def _make_uow() -> tuple[InMemoryUnitOfWork[GraphRepos], GraphRepos]:
    repos = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )
    return InMemoryUnitOfWork(repos), repos


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
    """UpdateNodeType stores a valid JSON Schema when provided."""
    uow, repos = _make_uow()
    nt = NodeType.create(slug="film", label="Film")
    await repos.node_types.add(nt)
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "year": {"title": "Year", "type": "number"},
        },
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


async def test_update_node_type_raises_on_invalid_schema() -> None:
    """UpdateNodeType rejects a schema that is not valid JSON Schema."""
    uow, repos = _make_uow()
    nt = NodeType.create(slug="film", label="Film")
    await repos.node_types.add(nt)
    use_case = UpdateNodeType(uow)

    with pytest.raises(InvalidSchemaError):
        await use_case.handle(
            UpdateNodeTypeCommand(
                node_type_id=nt.id,
                attributes_schema={"type": "not-a-valid-type"},
            ),
            SYSTEM_ACTOR,
        )


async def test_update_node_type_raises_when_missing() -> None:
    """UpdateNodeType raises NodeTypeNotFoundError when the node type doesn't exist."""
    uow, _ = _make_uow()
    use_case = UpdateNodeType(uow)

    with pytest.raises(NodeTypeNotFoundError):
        await use_case.handle(
            UpdateNodeTypeCommand(node_type_id=uuid.uuid4(), label="Ghost"),
            SYSTEM_ACTOR,
        )
