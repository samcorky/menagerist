"""Retention purge of items and connections on in-memory adapters."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.entrypoints.api.shared.access_guard import get_access_guard
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
from app.modules.graph.application.purge_expired_nodes import (
    PurgeExpiredNodes,
    PurgeExpiredNodesCommand,
    PurgeExpiredNodesResult,
)
from app.modules.graph.domain.edge import Edge
from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.errors import ForbiddenError, ValidationError
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

ALICE = uuid.UUID(int=101)
BOB = uuid.UUID(int=102)
NOW = datetime.now(UTC)
CUTOFF = NOW - timedelta(days=30)
LONG_AGO = NOW - timedelta(days=31)
MINUTE_AGO = NOW - timedelta(minutes=1)
EVERYONE = ContentFilter.everyone()


class _Dependents:
    """Records the items whose dependents were purged, and what the store held."""

    def __init__(self, repos: GraphRepos) -> None:
        self.purged: list[uuid.UUID] = []
        self._repos = repos
        self.item_still_stored: list[bool] = []
        self.on_purge: dict[uuid.UUID, Node] = {}

    async def purge_for_item(self, item_id: uuid.UUID) -> None:
        self.purged.append(item_id)
        self.item_still_stored.append(
            await self._repos.nodes.get_deleted(item_id, scope=EVERYONE) is not None
        )
        # Simulates a person restoring another item while this one is purged.
        if restored := self.on_purge.get(item_id):
            restored.deleted_at = None


def _repos() -> GraphRepos:
    return GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )


def _purge(repos: GraphRepos, dependents: _Dependents) -> PurgeExpiredNodes:
    return PurgeExpiredNodes(InMemoryUnitOfWork(repos), get_access_guard(), dependents)


async def _item(
    repos: GraphRepos,
    name: str,
    *,
    owner: uuid.UUID = ALICE,
    deleted_at: datetime | None = None,
) -> Node:
    node = Node.create(owner_id=owner, name=name, type=None)
    node.deleted_at = deleted_at
    await repos.nodes.add(node)
    return node


async def _edge(
    repos: GraphRepos,
    source: Node,
    target: Node,
    *,
    deleted_at: datetime | None = None,
    owner: uuid.UUID = ALICE,
) -> Edge:
    edge = Edge.create(
        owner_id=owner, source_id=source.id, target_id=target.id, type="knows"
    )
    edge.deleted_at = deleted_at
    await repos.edges.add(edge)
    return edge


async def _run(
    repos: GraphRepos,
    dependents: _Dependents | None = None,
    *,
    dry_run: bool = False,
    batch_size: int = 100,
) -> PurgeExpiredNodesResult:
    return await _purge(repos, dependents or _Dependents(repos)).handle(
        PurgeExpiredNodesCommand(
            older_than=CUTOFF, dry_run=dry_run, batch_size=batch_size
        ),
        SYSTEM_ACTOR,
    )


async def _node_ids(repos: GraphRepos) -> set[uuid.UUID]:
    store = repos.nodes
    assert isinstance(store, InMemoryNodeRepository)
    return set(store._nodes)


async def _edge_ids(repos: GraphRepos) -> set[uuid.UUID]:
    store = repos.edges
    assert isinstance(store, InMemoryEdgeRepository)
    return set(store._edges)


async def test_only_rows_deleted_before_the_cutoff_go_for_every_owner() -> None:
    """Old rows of both owners go; a minute-old one, and live ones, stay."""
    repos = _repos()
    old_alice = await _item(repos, "Old A", deleted_at=LONG_AGO)
    old_bob = await _item(repos, "Old B", owner=BOB, deleted_at=LONG_AGO)
    recent = await _item(repos, "Recent", deleted_at=MINUTE_AGO)
    live = await _item(repos, "Live")

    result = await _run(repos)

    assert result == PurgeExpiredNodesResult(items=2, connections=0)
    assert await _node_ids(repos) == {recent.id, live.id}
    assert old_alice.id not in await _node_ids(repos)
    assert old_bob.id not in await _node_ids(repos)


async def test_a_purged_item_takes_its_connections_and_dependents_first() -> None:
    """Live and deleted connections go with it; dependents are purged first."""
    repos = _repos()
    gone = await _item(repos, "Gone", deleted_at=LONG_AGO)
    friend = await _item(repos, "Friend")
    live_edge = await _edge(repos, gone, friend)
    deleted_edge = await _edge(repos, friend, gone, deleted_at=MINUTE_AGO)
    other = await _edge(repos, friend, await _item(repos, "Else"))
    dependents = _Dependents(repos)

    result = await _run(repos, dependents)

    assert result.items == 1
    assert dependents.purged == [gone.id]
    assert dependents.item_still_stored == [True]
    assert await _edge_ids(repos) == {other.id}
    assert live_edge.id not in await _edge_ids(repos)
    assert deleted_edge.id not in await _edge_ids(repos)


async def test_a_connection_deleted_on_its_own_goes_only_when_old_enough() -> None:
    """Both ends stay live; the old deleted connection goes, the recent one stays."""
    repos = _repos()
    a, b = await _item(repos, "A"), await _item(repos, "B")
    old = await _edge(repos, a, b, deleted_at=LONG_AGO)
    recent = await _edge(repos, b, a, deleted_at=MINUTE_AGO)
    live = await _edge(repos, a, b)

    result = await _run(repos)

    assert result == PurgeExpiredNodesResult(items=0, connections=1)
    assert await _edge_ids(repos) == {recent.id, live.id}
    assert old.id not in await _edge_ids(repos)


async def test_soft_deleted_types_are_never_touched() -> None:
    """Item and relationship types deleted long ago are not part of the purge."""
    repos = _repos()
    node_type = NodeType.create(slug="movie", label="Movie")
    node_type.deleted_at = LONG_AGO
    await repos.node_types.add(node_type)
    edge_type = EdgeType.create(slug="knows", label="Knows")
    edge_type.deleted_at = LONG_AGO
    await repos.edge_types.add(edge_type)

    result = await _run(repos)

    assert result == PurgeExpiredNodesResult(items=0, connections=0)
    assert isinstance(repos.node_types, InMemoryNodeTypeRepository)
    assert node_type.id in repos.node_types._node_types
    assert isinstance(repos.edge_types, InMemoryEdgeTypeRepository)
    assert edge_type.id in repos.edge_types._edge_types


async def test_dry_run_counts_and_changes_nothing() -> None:
    """The counts are what a real run would purge, and no dependents are touched."""
    repos = _repos()
    gone = await _item(repos, "Gone", deleted_at=LONG_AGO)
    friend = await _item(repos, "Friend")
    await _edge(repos, gone, friend)
    await _edge(repos, friend, gone, deleted_at=LONG_AGO)
    dependents = _Dependents(repos)
    nodes, edges = await _node_ids(repos), await _edge_ids(repos)

    dry = await _run(repos, dependents, dry_run=True)
    real = await _run(repos, dependents)

    assert dry == real == PurgeExpiredNodesResult(items=1, connections=1)
    assert nodes - await _node_ids(repos) == {gone.id}  # only the real run deleted
    assert len(edges) == 2
    assert dependents.purged == [gone.id]


async def test_a_second_run_does_nothing() -> None:
    """Repeating the purge finds nothing."""
    repos = _repos()
    await _item(repos, "Gone", deleted_at=LONG_AGO)
    await _run(repos)

    again = await _run(repos)

    assert again == PurgeExpiredNodesResult(items=0, connections=0)


async def test_more_rows_than_a_batch_are_all_purged_oldest_first() -> None:
    """Batches of two clear seven items and five connections, oldest first."""
    repos = _repos()
    hub = await _item(repos, "Hub")
    items = [
        await _item(repos, str(i), deleted_at=LONG_AGO - timedelta(minutes=i))
        for i in range(7)
    ]
    for i in range(5):
        await _edge(repos, hub, items[0], deleted_at=LONG_AGO + timedelta(minutes=i))
    dependents = _Dependents(repos)

    result = await _run(repos, dependents, batch_size=2)

    assert result == PurgeExpiredNodesResult(items=7, connections=5)
    assert dependents.purged == [i.id for i in reversed(items)]
    assert await _node_ids(repos) == {hub.id}
    assert await _edge_ids(repos) == set()


async def test_an_item_restored_since_it_was_listed_is_skipped() -> None:
    """A person restoring an item mid-run keeps it, and it is not counted."""
    repos = _repos()
    first = await _item(repos, "First", deleted_at=LONG_AGO - timedelta(days=1))
    second = await _item(repos, "Second", deleted_at=LONG_AGO)
    dependents = _Dependents(repos)
    dependents.on_purge[first.id] = second

    result = await _run(repos, dependents)

    assert result.items == 1
    assert dependents.purged == [first.id]
    assert await _node_ids(repos) == {second.id}


async def test_only_the_system_actor_may_run_it() -> None:
    """A signed-in person cannot trigger the instance-wide purge."""
    repos = _repos()
    person = Actor(id=ALICE, roles=frozenset({"admin"}))

    with pytest.raises(ForbiddenError):
        await _purge(repos, _Dependents(repos)).handle(
            PurgeExpiredNodesCommand(older_than=CUTOFF), person
        )


def test_the_command_refuses_a_naive_cutoff_and_an_empty_batch() -> None:
    """A cutoff needs a timezone and a batch needs at least one row."""
    with pytest.raises(ValidationError):
        PurgeExpiredNodesCommand(older_than=datetime(2026, 1, 1))
    with pytest.raises(ValidationError):
        PurgeExpiredNodesCommand(older_than=CUTOFF, batch_size=0)
