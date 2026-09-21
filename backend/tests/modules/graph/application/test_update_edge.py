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
from app.modules.graph.application.update_edge import UpdateEdge, UpdateEdgeCommand
from app.modules.graph.domain.edge import Edge
from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.domain.errors import EdgeNotFoundError, InvalidAttributesError
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork


async def test_update_edge_persists_and_commits() -> None:
    """UpdateEdge saves the changed edge and commits the unit of work."""
    repository = InMemoryEdgeRepository()
    edge = Edge.create(source_id=uuid.uuid4(), target_id=uuid.uuid4(), type="owns")
    await repository.add(edge)
    repos = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=repository,
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )
    uow = InMemoryUnitOfWork(repos)
    use_case = UpdateEdge(uow)

    result = await use_case.handle(
        UpdateEdgeCommand(edge_id=edge.id, attributes={"since": "1979"}),
        SYSTEM_ACTOR,
    )

    assert result.attributes == {"since": "1979"}
    stored = await repos.edges.get(edge.id)
    assert stored is not None
    assert stored.attributes == {"since": "1979"}
    assert uow.committed is True


async def test_update_edge_raises_when_missing() -> None:
    """UpdateEdge raises EdgeNotFoundError when the edge doesn't exist."""
    repos = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )
    uow = InMemoryUnitOfWork(repos)
    use_case = UpdateEdge(uow)

    with pytest.raises(EdgeNotFoundError):
        await use_case.handle(
            UpdateEdgeCommand(edge_id=uuid.uuid4(), attributes={}), SYSTEM_ACTOR
        )


async def test_update_edge_validates_attributes_against_schema() -> None:
    """UpdateEdge rejects attributes that violate the edge type's JSON Schema."""
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {"since": {"type": "string", "format": "date"}},
        "required": ["since"],
    }
    edge_types = InMemoryEdgeTypeRepository()
    await edge_types.add(
        EdgeType.create(slug="owns", label="Owns", attributes_schema=schema)
    )
    repository = InMemoryEdgeRepository()
    edge = Edge.create(source_id=uuid.uuid4(), target_id=uuid.uuid4(), type="owns")
    await repository.add(edge)
    repos = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=repository,
        node_types=InMemoryNodeTypeRepository(),
        edge_types=edge_types,
    )
    uow = InMemoryUnitOfWork(repos)
    use_case = UpdateEdge(uow)

    with pytest.raises(InvalidAttributesError):
        await use_case.handle(
            UpdateEdgeCommand(edge_id=edge.id, attributes={"since": "not-a-date"}),
            SYSTEM_ACTOR,
        )


async def test_update_edge_ignores_stale_invalid_value_that_was_not_edited() -> None:
    """A stale invalid value does not block editing another attribute."""
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "since": {"type": "string", "format": "date"},
            "note": {"type": "string"},
        },
    }
    edge_types = InMemoryEdgeTypeRepository()
    await edge_types.add(
        EdgeType.create(slug="owns", label="Owns", attributes_schema=schema)
    )
    repository = InMemoryEdgeRepository()
    edge = Edge.create(
        source_id=uuid.uuid4(),
        target_id=uuid.uuid4(),
        type="owns",
        attributes={"since": "long ago"},
    )
    await repository.add(edge)
    repos = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=repository,
        node_types=InMemoryNodeTypeRepository(),
        edge_types=edge_types,
    )
    use_case = UpdateEdge(InMemoryUnitOfWork(repos))

    result = await use_case.handle(
        UpdateEdgeCommand(
            edge_id=edge.id, attributes={"since": "long ago", "note": "gift"}
        ),
        SYSTEM_ACTOR,
    )
    assert result.attributes["note"] == "gift"

    with pytest.raises(InvalidAttributesError):
        await use_case.handle(
            UpdateEdgeCommand(edge_id=edge.id, attributes={"since": "yesterday"}),
            SYSTEM_ACTOR,
        )
