"""Deleted items: list, restore and purge on in-memory adapters."""

import uuid
from datetime import UTC, datetime, timedelta

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
from app.modules.graph.application.list_deleted_nodes import (
    ListDeletedNodes,
    ListDeletedNodesQuery,
)
from app.modules.graph.application.purge_deleted_node import (
    PurgeDeletedNode,
    PurgeDeletedNodeCommand,
)
from app.modules.graph.application.restore_node import RestoreNode, RestoreNodeCommand
from app.modules.graph.domain.edge import Edge
from app.modules.graph.domain.errors import NodeNotFoundError, NodeTypeDeletedError
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import Actor
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

ALICE = Actor(id=uuid.UUID(int=101), roles=frozenset({"member"}))
BOB = Actor(id=uuid.UUID(int=102), roles=frozenset({"member"}))
GUARD = InMemoryAccessGuard()


class _Dependents:
    """Records the items whose dependents were purged."""

    def __init__(self) -> None:
        self.purged: list[uuid.UUID] = []

    async def purge_for_item(self, item_id: uuid.UUID) -> None:
        self.purged.append(item_id)


def _repos() -> GraphRepos:
    return GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )


async def _item(
    repos: GraphRepos,
    name: str,
    *,
    owner: Actor = ALICE,
    deleted_ago: int | None = None,
    type: str | None = None,
) -> Node:
    node = Node.create(owner_id=owner.id, name=name, type=type)
    if deleted_ago is not None:
        node.soft_delete()
        node.deleted_at = datetime.now(UTC) - timedelta(minutes=deleted_ago)
    await repos.nodes.add(node)
    return node


def _list(repos: GraphRepos) -> ListDeletedNodes:
    return ListDeletedNodes(repos, GUARD)


def _restore(repos: GraphRepos) -> RestoreNode:
    return RestoreNode(InMemoryUnitOfWork(repos), GUARD)


def _purge(repos: GraphRepos, dependents: _Dependents) -> PurgeDeletedNode:
    return PurgeDeletedNode(InMemoryUnitOfWork(repos), GUARD, dependents)


async def test_list_shows_only_own_deleted_items_newest_first() -> None:
    """Live items and others' deleted content never appear; newest first."""
    repos = _repos()
    old = await _item(repos, "Old", deleted_ago=30)
    new = await _item(repos, "New", deleted_ago=5)
    await _item(repos, "Live")
    await _item(repos, "Theirs", owner=BOB, deleted_ago=1)

    result = await _list(repos).handle(ListDeletedNodesQuery(), ALICE)

    assert [n.id for n in result.items] == [new.id, old.id]
    assert result.total == 2


async def test_list_pages_by_the_last_row_id() -> None:
    """`after` continues past the previous page; the total stays whole."""
    repos = _repos()
    rows = [await _item(repos, str(i), deleted_ago=i) for i in range(1, 6)]
    # Newest deleted first is the smallest `deleted_ago`.
    first = await _list(repos).handle(ListDeletedNodesQuery(limit=2), ALICE)
    second = await _list(repos).handle(
        ListDeletedNodesQuery(after=first.items[-1].id, limit=2), ALICE
    )
    third = await _list(repos).handle(
        ListDeletedNodesQuery(after=second.items[-1].id, limit=2), ALICE
    )

    assert [n.id for n in first.items + second.items + third.items] == [
        r.id for r in rows
    ]
    assert first.total == second.total == third.total == 5


async def test_list_after_an_id_no_longer_in_recently_deleted_is_empty() -> None:
    """A stale cursor yields an empty page rather than restarting."""
    repos = _repos()
    await _item(repos, "A", deleted_ago=1)

    result = await _list(repos).handle(ListDeletedNodesQuery(after=uuid.uuid7()), ALICE)

    assert result.items == []


async def test_restore_clears_only_the_mark_and_keeps_live_connections() -> None:
    """The item returns; its live edge is untouched and a deleted edge stays deleted."""
    repos = _repos()
    item = await _item(repos, "Alien", deleted_ago=3)
    other = await _item(repos, "Ripley")
    live = Edge.create(
        owner_id=ALICE.id, source_id=item.id, target_id=other.id, type="knows"
    )
    gone = Edge.create(
        owner_id=ALICE.id, source_id=other.id, target_id=item.id, type="knows"
    )
    gone.soft_delete()
    await repos.edges.add(live)
    await repos.edges.add(gone)

    result = await _restore(repos).handle(RestoreNodeCommand(node_id=item.id), ALICE)

    assert result.deleted_at is None
    assert await repos.nodes.get(item.id, scope=GUARD.scope_for(ALICE)) is not None
    assert (
        await repos.nodes.get_deleted(item.id, scope=GUARD.scope_for(ALICE))
    ) is None
    assert live.deleted_at is None
    assert gone.deleted_at is not None


async def test_restore_an_item_whose_type_exists() -> None:
    """A live item type does not block."""
    repos = _repos()
    await repos.node_types.add(NodeType.create(slug="film", label="Film"))
    item = await _item(repos, "Alien", deleted_ago=1, type="film")

    result = await _restore(repos).handle(RestoreNodeCommand(node_id=item.id), ALICE)

    assert result.type == "film"


async def test_restore_refuses_when_the_item_type_was_deleted() -> None:
    """A deleted type is a 409 naming the slug; the item stays deleted."""
    repos = _repos()
    node_type = NodeType.create(slug="film", label="Film")
    node_type.soft_delete()
    await repos.node_types.add(node_type)
    item = await _item(repos, "Alien", deleted_ago=1, type="film")

    with pytest.raises(NodeTypeDeletedError, match="film"):
        await _restore(repos).handle(RestoreNodeCommand(node_id=item.id), ALICE)

    assert await repos.nodes.get_deleted(item.id, scope=GUARD.scope_for(ALICE))


@pytest.mark.parametrize("who", ["live", "unknown", "foreign"])
async def test_restore_only_finds_own_deleted_items(who: str) -> None:
    """A live, unknown or another person's item is not found."""
    repos = _repos()
    live = await _item(repos, "Live")
    foreign = await _item(repos, "Theirs", owner=BOB, deleted_ago=1)
    target = {"live": live.id, "unknown": uuid.uuid7(), "foreign": foreign.id}[who]

    with pytest.raises(NodeNotFoundError):
        await _restore(repos).handle(RestoreNodeCommand(node_id=target), ALICE)


async def test_purge_removes_the_item_its_connections_and_dependents() -> None:
    """Edges (live and deleted) and the item go; the dependents port is asked."""
    repos = _repos()
    dependents = _Dependents()
    item = await _item(repos, "Alien", deleted_ago=3)
    other = await _item(repos, "Ripley")
    edges = [
        Edge.create(
            owner_id=ALICE.id, source_id=item.id, target_id=other.id, type="knows"
        ),
        Edge.create(
            owner_id=ALICE.id, source_id=other.id, target_id=item.id, type="knows"
        ),
    ]
    edges[1].soft_delete()
    third = await _item(repos, "Newt")
    keep = Edge.create(
        owner_id=ALICE.id, source_id=other.id, target_id=third.id, type="knows"
    )
    for edge in (*edges, keep):
        await repos.edges.add(edge)
    uow = InMemoryUnitOfWork(repos)

    await PurgeDeletedNode(uow, GUARD, dependents).handle(
        PurgeDeletedNodeCommand(node_id=item.id), ALICE
    )

    everyone = ContentFilter.everyone()
    assert uow.committed
    assert dependents.purged == [item.id]
    assert await repos.nodes.get_deleted(item.id, scope=everyone) is None
    assert await repos.nodes.get(other.id, scope=everyone) is not None
    assert await repos.edges.get(edges[0].id, scope=everyone) is None
    assert await repos.edges.get(keep.id, scope=everyone) is not None


@pytest.mark.parametrize("who", ["live", "unknown", "foreign"])
async def test_purge_refuses_anything_not_in_the_callers_recently_deleted(
    who: str,
) -> None:
    """A live item, an unknown id and another person's deleted item are 404s."""
    repos = _repos()
    dependents = _Dependents()
    live = await _item(repos, "Live")
    foreign = await _item(repos, "Theirs", owner=BOB, deleted_ago=1)
    target = {"live": live.id, "unknown": uuid.uuid7(), "foreign": foreign.id}[who]

    with pytest.raises(NodeNotFoundError):
        await _purge(repos, dependents).handle(
            PurgeDeletedNodeCommand(node_id=target), ALICE
        )

    assert dependents.purged == []
    assert await repos.nodes.get(live.id, scope=GUARD.scope_for(ALICE)) is not None
    assert await repos.nodes.get_deleted(foreign.id, scope=GUARD.scope_for(BOB))
