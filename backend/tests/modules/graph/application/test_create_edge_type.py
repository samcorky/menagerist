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
from app.modules.graph.application.create_edge_type import (
    CreateEdgeType,
    CreateEdgeTypeCommand,
)
from app.modules.graph.domain.errors import (
    EdgeTypeSlugConflictError,
    InvalidSchemaError,
)
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


async def test_create_edge_type_persists_and_commits() -> None:
    """CreateEdgeType adds the edge type to the repository and commits."""
    uow, repos = _make_uow()
    use_case = CreateEdgeType(uow)

    et = await use_case.handle(
        CreateEdgeTypeCommand(slug="directed-by", label="Directed By"),
        SYSTEM_ACTOR,
    )

    assert await repos.edge_types.get(et.id) is et
    assert uow.committed is True


async def test_create_edge_type_persists_attributes_schema() -> None:
    """CreateEdgeType stores a valid JSON Schema when provided."""
    uow, repos = _make_uow()
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "since": {"title": "Since", "type": "string", "format": "date"},
        },
    }
    use_case = CreateEdgeType(uow)

    et = await use_case.handle(
        CreateEdgeTypeCommand(
            slug="directed-by", label="Directed By", attributes_schema=schema
        ),
        SYSTEM_ACTOR,
    )

    stored = await repos.edge_types.get(et.id)
    assert stored is not None
    assert stored.attributes_schema == schema


async def test_create_edge_type_raises_on_invalid_schema() -> None:
    """CreateEdgeType rejects a schema that is not valid JSON Schema."""
    uow, _ = _make_uow()
    use_case = CreateEdgeType(uow)

    with pytest.raises(InvalidSchemaError):
        await use_case.handle(
            CreateEdgeTypeCommand(
                slug="directed-by",
                label="Directed By",
                attributes_schema={"type": "not-a-valid-type"},
            ),
            SYSTEM_ACTOR,
        )


async def test_create_edge_type_raises_on_slug_conflict() -> None:
    """CreateEdgeType raises EdgeTypeSlugConflictError when slug already exists."""
    uow, _ = _make_uow()
    use_case = CreateEdgeType(uow)
    await use_case.handle(
        CreateEdgeTypeCommand(slug="directed-by", label="Directed By"), SYSTEM_ACTOR
    )

    with pytest.raises(EdgeTypeSlugConflictError):
        await use_case.handle(
            CreateEdgeTypeCommand(slug="directed-by", label="Duplicate"),
            SYSTEM_ACTOR,
        )
