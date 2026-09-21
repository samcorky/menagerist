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
from app.modules.graph.application.create_node import CreateNode, CreateNodeCommand
from app.modules.graph.domain.errors import InvalidAttributesError
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


async def test_create_node_persists_and_commits() -> None:
    """CreateNode adds the node to the repository and commits the unit of work."""
    uow, repos = _make_uow()
    use_case = CreateNode(uow)

    node = await use_case.handle(
        CreateNodeCommand(name="Alien", type="film", attributes={"title": "Alien"}),
        SYSTEM_ACTOR,
    )

    assert await repos.nodes.get(node.id) is node
    assert uow.committed is True


async def test_create_node_validates_attributes_against_schema() -> None:
    """CreateNode rejects attributes that violate the node type's JSON Schema."""
    uow, repos = _make_uow()
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {"year": {"type": "number"}},
        "required": ["year"],
    }
    await repos.node_types.add(
        NodeType.create(slug="film", label="Film", attributes_schema=schema)
    )
    use_case = CreateNode(uow)

    with pytest.raises(InvalidAttributesError):
        await use_case.handle(
            CreateNodeCommand(
                name="Alien", type="film", attributes={"year": "not-a-number"}
            ),
            SYSTEM_ACTOR,
        )


async def test_create_node_passes_valid_attributes() -> None:
    """CreateNode accepts attributes that conform to the node type's JSON Schema."""
    uow, repos = _make_uow()
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {"year": {"type": "number"}},
        "required": ["year"],
    }
    await repos.node_types.add(
        NodeType.create(slug="film", label="Film", attributes_schema=schema)
    )
    use_case = CreateNode(uow)

    node = await use_case.handle(
        CreateNodeCommand(name="Alien", type="film", attributes={"year": 1979}),
        SYSTEM_ACTOR,
    )

    assert node.attributes["year"] == 1979


async def test_create_node_ignores_required_in_schema() -> None:
    """A missing required attribute never blocks creation (required is advisory)."""
    uow, repos = _make_uow()
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {"year": {"type": "number"}},
        "required": ["year"],
        "x-menagerist": {"required": ["year"]},
    }
    await repos.node_types.add(
        NodeType.create(slug="film", label="Film", attributes_schema=schema)
    )
    use_case = CreateNode(uow)

    node = await use_case.handle(
        CreateNodeCommand(name="Alien", type="film", attributes={}),
        SYSTEM_ACTOR,
    )

    assert node.attributes == {}
