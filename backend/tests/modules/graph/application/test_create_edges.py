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
from app.modules.graph.application.create_edges import CreateEdges, CreateEdgesCommand
from app.modules.graph.domain.edge import Edge
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
from app.shared_kernel.errors import ValidationError
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork


async def _repos_with_source_and_targets(
    count: int,
) -> tuple[GraphRepos, Node, list[Node]]:
    node_repo = InMemoryNodeRepository()
    source = Node.create(owner_id=uuid.UUID(int=1), name="Photo", type="photo")
    await node_repo.add(source)
    targets = [
        Node.create(owner_id=uuid.UUID(int=1), name=f"Person {i}", type="person")
        for i in range(count)
    ]
    for target in targets:
        await node_repo.add(target)
    repos = GraphRepos(
        nodes=node_repo,
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )
    return repos, source, targets


async def test_create_edges_connects_every_target_and_commits() -> None:
    """CreateEdges makes one edge per target and commits once."""
    repos, source, targets = await _repos_with_source_and_targets(3)
    uow = InMemoryUnitOfWork(repos)

    result = await CreateEdges(uow, InMemoryAccessGuard()).handle(
        CreateEdgesCommand(
            source_id=source.id,
            target_ids=[t.id for t in targets],
            type="pictured-with",
        ),
        SYSTEM_ACTOR,
    )

    assert {e.target_id for e in result.created} == {t.id for t in targets}
    assert result.skipped == []
    assert uow.committed is True
    stored = await repos.edges.list_for_node(
        source.id, after=None, limit=10, scope=ContentFilter.everyone()
    )
    assert len(stored) == 3


async def test_create_edges_skips_a_target_already_connected() -> None:
    """A target already linked by an edge of the same type is skipped."""
    repos, source, targets = await _repos_with_source_and_targets(2)
    existing = Edge.create(
        owner_id=uuid.UUID(int=1),
        source_id=source.id,
        target_id=targets[0].id,
        type="pictured-with",
    )
    await repos.edges.add(existing)

    result = await CreateEdges(InMemoryUnitOfWork(repos), InMemoryAccessGuard()).handle(
        CreateEdgesCommand(
            source_id=source.id,
            target_ids=[t.id for t in targets],
            type="pictured-with",
        ),
        SYSTEM_ACTOR,
    )

    assert result.skipped == [targets[0].id]
    assert [e.target_id for e in result.created] == [targets[1].id]


async def test_create_edges_does_not_skip_a_different_type() -> None:
    """An edge of a different type does not block a new one to the same target."""
    repos, source, targets = await _repos_with_source_and_targets(1)
    other_type = Edge.create(
        owner_id=uuid.UUID(int=1),
        source_id=source.id,
        target_id=targets[0].id,
        type="tagged-in",
    )
    await repos.edges.add(other_type)

    result = await CreateEdges(InMemoryUnitOfWork(repos), InMemoryAccessGuard()).handle(
        CreateEdgesCommand(
            source_id=source.id, target_ids=[targets[0].id], type="pictured-with"
        ),
        SYSTEM_ACTOR,
    )

    assert result.skipped == []
    assert len(result.created) == 1


async def test_create_edges_treats_an_incoming_edge_as_already_connected() -> None:
    """A pre-existing edge in the other direction still counts as connected."""
    repos, source, targets = await _repos_with_source_and_targets(1)
    reverse = Edge.create(
        owner_id=uuid.UUID(int=1),
        source_id=targets[0].id,
        target_id=source.id,
        type="pictured-with",
    )
    await repos.edges.add(reverse)

    result = await CreateEdges(InMemoryUnitOfWork(repos), InMemoryAccessGuard()).handle(
        CreateEdgesCommand(
            source_id=source.id, target_ids=[targets[0].id], type="pictured-with"
        ),
        SYSTEM_ACTOR,
    )

    assert result.skipped == [targets[0].id]
    assert result.created == []


async def test_create_edges_raises_for_a_missing_source() -> None:
    """An unknown source id is a not-found error and nothing is created."""
    repos, _source, targets = await _repos_with_source_and_targets(1)

    with pytest.raises(NodeNotFoundError):
        await CreateEdges(InMemoryUnitOfWork(repos), InMemoryAccessGuard()).handle(
            CreateEdgesCommand(
                source_id=uuid.uuid4(), target_ids=[targets[0].id], type="pictured-with"
            ),
            SYSTEM_ACTOR,
        )


async def test_create_edges_raises_for_a_missing_target() -> None:
    """An unknown target id is a not-found error, mid-batch."""
    repos, source, targets = await _repos_with_source_and_targets(1)

    with pytest.raises(NodeNotFoundError):
        await CreateEdges(InMemoryUnitOfWork(repos), InMemoryAccessGuard()).handle(
            CreateEdgesCommand(
                source_id=source.id,
                target_ids=[targets[0].id, uuid.uuid4()],
                type="pictured-with",
            ),
            SYSTEM_ACTOR,
        )


async def test_create_edges_validates_attributes_against_the_type_schema() -> None:
    """Shared attributes are validated against the edge type's schema once."""
    repos, source, targets = await _repos_with_source_and_targets(2)
    await repos.edge_types.add(
        EdgeType.create(
            owner_id=uuid.UUID(int=1),
            slug="pictured-with",
            label="Pictured with",
            attributes_schema={
                "type": "object",
                "properties": {"since": {"type": "string", "format": "date"}},
            },
        )
    )

    with pytest.raises(InvalidAttributesError):
        await CreateEdges(InMemoryUnitOfWork(repos), InMemoryAccessGuard()).handle(
            CreateEdgesCommand(
                source_id=source.id,
                target_ids=[t.id for t in targets],
                type="pictured-with",
                attributes={"since": "not-a-date"},
            ),
            SYSTEM_ACTOR,
        )


async def test_create_edges_auto_creates_an_unknown_edge_type() -> None:
    """An unknown type slug creates the edge type, as CreateEdge already does."""
    repos, source, targets = await _repos_with_source_and_targets(1)

    await CreateEdges(InMemoryUnitOfWork(repos), InMemoryAccessGuard()).handle(
        CreateEdgesCommand(
            source_id=source.id, target_ids=[targets[0].id], type="pictured-with"
        ),
        SYSTEM_ACTOR,
    )

    assert (
        await repos.edge_types.get_by_slug(
            "pictured-with", scope=ContentFilter.everyone()
        )
        is not None
    )


async def test_create_edges_reverse_connects_each_target_to_the_shared_item() -> None:
    """With reverse, every target is the start of its own edge into the source."""
    repos, box, items = await _repos_with_source_and_targets(3)

    result = await CreateEdges(InMemoryUnitOfWork(repos), InMemoryAccessGuard()).handle(
        CreateEdgesCommand(
            source_id=box.id,
            target_ids=[i.id for i in items],
            type="stored-in",
            reverse=True,
        ),
        SYSTEM_ACTOR,
    )

    assert {(e.source_id, e.target_id) for e in result.created} == {
        (i.id, box.id) for i in items
    }
    assert result.skipped == []


async def test_create_edges_reverse_skips_an_existing_connection() -> None:
    """An existing edge of the same type, in either direction, is skipped."""
    repos, box, items = await _repos_with_source_and_targets(2)
    await repos.edges.add(
        Edge.create(
            owner_id=uuid.UUID(int=1),
            source_id=items[0].id,
            target_id=box.id,
            type="stored-in",
        )
    )

    result = await CreateEdges(InMemoryUnitOfWork(repos), InMemoryAccessGuard()).handle(
        CreateEdgesCommand(
            source_id=box.id,
            target_ids=[i.id for i in items],
            type="stored-in",
            reverse=True,
        ),
        SYSTEM_ACTOR,
    )

    assert result.skipped == [items[0].id]
    assert [e.source_id for e in result.created] == [items[1].id]


@pytest.mark.parametrize("reverse", [False, True])
async def test_create_edges_refuses_to_connect_an_item_to_itself(reverse: bool) -> None:
    """The source appearing among the targets is refused and nothing is created."""
    repos, box, items = await _repos_with_source_and_targets(1)

    with pytest.raises(ValidationError):
        await CreateEdges(InMemoryUnitOfWork(repos), InMemoryAccessGuard()).handle(
            CreateEdgesCommand(
                source_id=box.id,
                target_ids=[items[0].id, box.id],
                type="stored-in",
                reverse=reverse,
            ),
            SYSTEM_ACTOR,
        )

    assert (
        await repos.edges.list_for_node(
            box.id, after=None, limit=10, scope=ContentFilter.everyone()
        )
        == []
    )


async def _with_limit(
    repos: GraphRepos,
    *,
    source_types: tuple[str, ...] = (),
    target_types: tuple[str, ...] = (),
) -> None:
    await repos.edge_types.add(
        EdgeType.create(
            owner_id=SYSTEM_ACTOR.id,
            slug="pictured-with",
            label="Pictured with",
            source_types=source_types,
            target_types=target_types,
        )
    )


async def test_create_edges_checks_each_target_against_the_limit() -> None:
    """One target of the wrong type refuses the batch and creates nothing."""
    repos, source, targets = await _repos_with_source_and_targets(2)
    film = Node.create(owner_id=uuid.UUID(int=1), name="Film", type="film")
    await repos.nodes.add(film)
    await _with_limit(repos, target_types=("person",))
    uow = InMemoryUnitOfWork(repos)

    with pytest.raises(ItemTypeNotAllowedError, match="Film"):
        await CreateEdges(uow, InMemoryAccessGuard()).handle(
            CreateEdgesCommand(
                source_id=source.id,
                target_ids=[targets[0].id, film.id],
                type="pictured-with",
            ),
            SYSTEM_ACTOR,
        )

    assert uow.committed is False
    assert (
        await repos.edges.list_for_node(
            source.id, after=None, limit=10, scope=ContentFilter.everyone()
        )
        == []
    )


async def test_create_edges_reverse_checks_the_shared_item_as_the_target() -> None:
    """With `reverse` each target starts its edge, so limits swap ends."""
    repos, shared, others = await _repos_with_source_and_targets(2)
    await _with_limit(repos, source_types=("person",), target_types=("photo",))

    result = await CreateEdges(InMemoryUnitOfWork(repos), InMemoryAccessGuard()).handle(
        CreateEdgesCommand(
            source_id=shared.id,
            target_ids=[o.id for o in others],
            type="pictured-with",
            reverse=True,
        ),
        SYSTEM_ACTOR,
    )
    assert len(result.created) == 2

    # The same limit refuses the unreversed batch: the photo would be the source.
    repos, shared, others = await _repos_with_source_and_targets(2)
    await _with_limit(repos, source_types=("person",), target_types=("photo",))
    with pytest.raises(ItemTypeNotAllowedError, match="at its source"):
        await CreateEdges(InMemoryUnitOfWork(repos), InMemoryAccessGuard()).handle(
            CreateEdgesCommand(
                source_id=shared.id,
                target_ids=[o.id for o in others],
                type="pictured-with",
            ),
            SYSTEM_ACTOR,
        )


async def test_create_edges_does_not_recheck_targets_already_connected() -> None:
    """An existing connection is left alone, even if it no longer fits."""
    repos, source, targets = await _repos_with_source_and_targets(1)
    command = CreateEdgesCommand(
        source_id=source.id, target_ids=[targets[0].id], type="pictured-with"
    )
    await CreateEdges(InMemoryUnitOfWork(repos), InMemoryAccessGuard()).handle(
        command, SYSTEM_ACTOR
    )
    edge_type = await repos.edge_types.get_by_slug(
        "pictured-with", scope=ContentFilter.everyone()
    )
    assert edge_type is not None
    edge_type.update(target_types=["film"])
    await repos.edge_types.save(edge_type)

    result = await CreateEdges(InMemoryUnitOfWork(repos), InMemoryAccessGuard()).handle(
        command, SYSTEM_ACTOR
    )

    assert result.skipped == [targets[0].id]
