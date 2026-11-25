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
from app.modules.graph.application.create_edge import CreateEdge, CreateEdgeCommand
from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.domain.errors import (
    InvalidAttributesError,
    ItemTypeNotAllowedError,
    NodeNotFoundError,
)
from app.modules.graph.domain.node import Node
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork


async def _repos_with_two_nodes() -> tuple[GraphRepos, Node, Node]:
    node_repo = InMemoryNodeRepository()
    source = Node.create(owner_id=uuid.UUID(int=1), name="Alien", type="film")
    target = Node.create(owner_id=uuid.UUID(int=1), name="Ridley Scott", type="person")
    await node_repo.add(source)
    await node_repo.add(target)
    return (
        GraphRepos(
            nodes=node_repo,
            edges=InMemoryEdgeRepository(),
            node_types=InMemoryNodeTypeRepository(),
            edge_types=InMemoryEdgeTypeRepository(),
        ),
        source,
        target,
    )


async def test_create_edge_persists_and_commits() -> None:
    """CreateEdge adds the edge to the repository and commits the unit of work."""
    repos, source, target = await _repos_with_two_nodes()
    uow = InMemoryUnitOfWork(repos)
    use_case = CreateEdge(uow, InMemoryAccessGuard())

    edge = await use_case.handle(
        CreateEdgeCommand(source_id=source.id, target_id=target.id, type="directed-by"),
        SYSTEM_ACTOR,
    )

    assert await repos.edges.get(edge.id, scope=ContentFilter.everyone()) is edge
    assert uow.committed is True


async def test_create_edge_raises_when_source_missing() -> None:
    """CreateEdge raises NodeNotFoundError when the source node doesn't exist."""
    repos, _source, target = await _repos_with_two_nodes()
    uow = InMemoryUnitOfWork(repos)
    use_case = CreateEdge(uow, InMemoryAccessGuard())

    with pytest.raises(NodeNotFoundError):
        await use_case.handle(
            CreateEdgeCommand(
                source_id=uuid.uuid4(), target_id=target.id, type="directed-by"
            ),
            SYSTEM_ACTOR,
        )


async def test_create_edge_raises_when_target_missing() -> None:
    """CreateEdge raises NodeNotFoundError when the target node doesn't exist."""
    repos, source, _target = await _repos_with_two_nodes()
    uow = InMemoryUnitOfWork(repos)
    use_case = CreateEdge(uow, InMemoryAccessGuard())

    with pytest.raises(NodeNotFoundError):
        await use_case.handle(
            CreateEdgeCommand(
                source_id=source.id, target_id=uuid.uuid4(), type="directed-by"
            ),
            SYSTEM_ACTOR,
        )


async def test_create_edge_validates_attributes_against_schema() -> None:
    """CreateEdge rejects attributes that violate the edge type's JSON Schema."""
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {"since": {"type": "string", "format": "date"}},
        "required": ["since"],
    }
    repos, source, target = await _repos_with_two_nodes()
    await repos.edge_types.add(
        EdgeType.create(
            owner_id=uuid.UUID(int=1),
            slug="directed-by",
            label="Directed By",
            attributes_schema=schema,
        )
    )
    uow = InMemoryUnitOfWork(repos)
    use_case = CreateEdge(uow, InMemoryAccessGuard())

    with pytest.raises(InvalidAttributesError):
        await use_case.handle(
            CreateEdgeCommand(
                source_id=source.id,
                target_id=target.id,
                type="directed-by",
                attributes={"since": "not-a-date"},
            ),
            SYSTEM_ACTOR,
        )


async def _limited(
    repos: GraphRepos,
    *,
    source_types: tuple[str, ...] = (),
    target_types: tuple[str, ...] = (),
) -> None:
    await repos.edge_types.add(
        EdgeType.create(
            owner_id=SYSTEM_ACTOR.id,
            slug="directed-by",
            label="Directed by",
            source_types=source_types,
            target_types=target_types,
        )
    )


async def test_create_edge_allows_items_inside_the_limits() -> None:
    """A film joined to a person satisfies "film to person"."""
    repos, source, target = await _repos_with_two_nodes()
    await _limited(repos, source_types=("film",), target_types=("person",))

    edge = await CreateEdge(InMemoryUnitOfWork(repos), InMemoryAccessGuard()).handle(
        CreateEdgeCommand(source_id=source.id, target_id=target.id, type="directed-by"),
        SYSTEM_ACTOR,
    )

    assert edge.type == "directed-by"


@pytest.mark.parametrize(
    ("source_types", "target_types", "message"),
    [
        ((), ("film",), "joins only film at its target"),
        (("person", "place"), (), "person, place at its source"),
    ],
)
async def test_create_edge_refuses_an_item_outside_a_limit(
    source_types: tuple[str, ...], target_types: tuple[str, ...], message: str
) -> None:
    """The error names the end, the allowed types and the item's own type."""
    repos, source, target = await _repos_with_two_nodes()
    await _limited(repos, source_types=source_types, target_types=target_types)
    uow = InMemoryUnitOfWork(repos)

    with pytest.raises(ItemTypeNotAllowedError, match=message):
        await CreateEdge(uow, InMemoryAccessGuard()).handle(
            CreateEdgeCommand(
                source_id=source.id, target_id=target.id, type="directed-by"
            ),
            SYSTEM_ACTOR,
        )

    assert uow.committed is False


async def test_create_edge_refuses_an_untyped_item_under_a_limit() -> None:
    """An item with no type is never one of the listed types."""
    repos, source, _ = await _repos_with_two_nodes()
    untyped = Node.create(owner_id=uuid.UUID(int=1), name="Mystery")
    await repos.nodes.add(untyped)
    await _limited(repos, target_types=("person",))

    with pytest.raises(ItemTypeNotAllowedError, match="no type"):
        await CreateEdge(InMemoryUnitOfWork(repos), InMemoryAccessGuard()).handle(
            CreateEdgeCommand(
                source_id=source.id, target_id=untyped.id, type="directed-by"
            ),
            SYSTEM_ACTOR,
        )
