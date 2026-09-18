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
from app.modules.graph.application.update_edge_type import (
    UpdateEdgeType,
    UpdateEdgeTypeCommand,
)
from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.domain.errors import EdgeTypeNotFoundError, InvalidSchemaError
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
    """UpdateEdgeType stores a valid JSON Schema when provided."""
    uow, repos = _make_uow()
    et = EdgeType.create(slug="directed-by", label="Directed By")
    await repos.edge_types.add(et)
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "since": {"title": "Since", "type": "string", "format": "date"},
        },
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


async def test_update_edge_type_raises_on_invalid_schema() -> None:
    """UpdateEdgeType rejects a schema that is not valid JSON Schema."""
    uow, repos = _make_uow()
    et = EdgeType.create(slug="directed-by", label="Directed By")
    await repos.edge_types.add(et)
    use_case = UpdateEdgeType(uow)

    with pytest.raises(InvalidSchemaError):
        await use_case.handle(
            UpdateEdgeTypeCommand(
                edge_type_id=et.id,
                attributes_schema={"type": "not-a-valid-type"},
            ),
            SYSTEM_ACTOR,
        )


async def test_update_edge_type_raises_when_missing() -> None:
    """UpdateEdgeType raises EdgeTypeNotFoundError when the edge type doesn't exist."""
    uow, _ = _make_uow()
    use_case = UpdateEdgeType(uow)

    with pytest.raises(EdgeTypeNotFoundError):
        await use_case.handle(
            UpdateEdgeTypeCommand(edge_type_id=uuid.uuid4(), label="Ghost"),
            SYSTEM_ACTOR,
        )
