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
from app.modules.graph.application.create_edge_type import (
    CreateEdgeType,
    CreateEdgeTypeCommand,
)
from app.modules.graph.domain.errors import EdgeTypeSlugConflictError
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
    """CreateEdgeType stores attributes_schema when provided."""
    uow, repos = _make_uow()
    schema = {
        "fields": [
            {"key": "since", "label": "Since", "type": "date", "required": False}
        ]
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
