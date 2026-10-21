"""Connection use cases with two people: ownership is stamped and enforced."""

import uuid
from typing import TYPE_CHECKING, Any

import pytest

from app.entrypoints.api.shared.access_policy import OwnerAccessPolicy
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
from app.modules.graph.application.count_edge_type_attribute_usage import (
    CountEdgeTypeAttributeUsage,
    CountEdgeTypeAttributeUsageQuery,
)
from app.modules.graph.application.create_edge import CreateEdge, CreateEdgeCommand
from app.modules.graph.application.create_edges import CreateEdges, CreateEdgesCommand
from app.modules.graph.application.delete_edge import DeleteEdge, DeleteEdgeCommand
from app.modules.graph.application.get_edge import GetEdge, GetEdgeQuery
from app.modules.graph.application.list_edges import ListEdges, ListEdgesQuery
from app.modules.graph.application.update_edge import UpdateEdge, UpdateEdgeCommand
from app.modules.graph.domain.edge import Edge
from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.domain.errors import EdgeNotFoundError, NodeNotFoundError
from app.modules.graph.domain.node import Node
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.actor import Actor
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

if TYPE_CHECKING:
    from app.shared_kernel.access_policy import AccessPolicy

ALICE = Actor(id=uuid.UUID(int=101), roles=frozenset({"member"}))
BOB = Actor(id=uuid.UUID(int=102), roles=frozenset({"member"}))
POLICY = OwnerAccessPolicy()


class _SpyEdges(InMemoryEdgeRepository):
    """Counts writes, because the in-memory unit of work does not roll back."""

    def __init__(self) -> None:
        super().__init__()
        self.writes = 0

    async def add(self, edge: Edge) -> None:
        self.writes += 1
        await super().add(edge)

    async def save(self, edge: Edge) -> None:
        self.writes += 1
        await super().save(edge)


class _RecordingPolicy:
    """Wraps the real policy and records which check each use case asks for."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self._inner: AccessPolicy = OwnerAccessPolicy()

    def scope_for(self, actor: Actor) -> ContentFilter:
        self.calls.append("scope")
        return self._inner.scope_for(actor)

    def assert_can_view(self, actor: Actor, owner_id: uuid.UUID | None) -> None:
        self.calls.append("view")
        self._inner.assert_can_view(actor, owner_id)

    def assert_can_modify(self, actor: Actor, owner_id: uuid.UUID | None) -> None:
        self.calls.append("modify")
        self._inner.assert_can_modify(actor, owner_id)

    def assert_can_delete(self, actor: Actor, owner_id: uuid.UUID | None) -> None:
        self.calls.append("delete")
        self._inner.assert_can_delete(actor, owner_id)


def _repos() -> tuple[GraphRepos, _SpyEdges]:
    edges = _SpyEdges()
    repos = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=edges,
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )
    return repos, edges


async def _item(repos: GraphRepos, owner: Actor, name: str = "Item") -> Node:
    node = Node.create(owner_id=owner.id, name=name)
    await repos.nodes.add(node)
    return node


async def _connection(
    repos: GraphRepos,
    owner: Actor,
    type_: str = "related-to",
    attributes: dict[str, Any] | None = None,
) -> Edge:
    source = await _item(repos, owner)
    target = await _item(repos, owner)
    edge = Edge.create(
        owner_id=owner.id,
        source_id=source.id,
        target_id=target.id,
        type=type_,
        attributes=attributes,
    )
    await repos.edges.add(edge)
    return edge


async def test_create_edge_stamps_the_actor_as_owner() -> None:
    """The creator owns the new connection; only they can then see it."""
    repos, _ = _repos()
    source, target = await _item(repos, ALICE), await _item(repos, ALICE)
    uow = InMemoryUnitOfWork(repos)

    edge = await CreateEdge(uow, POLICY).handle(
        CreateEdgeCommand(source_id=source.id, target_id=target.id, type="owns"), ALICE
    )

    assert uow.committed is True
    assert edge.owner_id == ALICE.id
    assert await repos.edges.get(edge.id, scope=ContentFilter.of(ALICE.id)) is edge
    assert await repos.edges.get(edge.id, scope=ContentFilter.of(BOB.id)) is None


@pytest.mark.parametrize("foreign_end", ["source", "target"])
async def test_create_edge_to_someone_elses_item_is_not_found_and_writes_nothing(
    foreign_end: str,
) -> None:
    """Both endpoints must be visible: a foreign one answers like a missing one."""
    repos, edges = _repos()
    mine = await _item(repos, ALICE)
    theirs = await _item(repos, BOB)
    source, target = (theirs, mine) if foreign_end == "source" else (mine, theirs)
    uow = InMemoryUnitOfWork(repos)

    with pytest.raises(NodeNotFoundError):
        await CreateEdge(uow, POLICY).handle(
            CreateEdgeCommand(source_id=source.id, target_id=target.id, type="owns"),
            ALICE,
        )

    assert edges.writes == 0
    assert await repos.edge_types.get_by_slug("owns") is None
    assert not uow.committed


async def test_create_edges_with_one_foreign_endpoint_creates_nothing() -> None:
    """A batch containing one foreign target fails before any edge is written."""
    repos, edges = _repos()
    source = await _item(repos, ALICE)
    mine = await _item(repos, ALICE)
    theirs = await _item(repos, BOB)
    uow = InMemoryUnitOfWork(repos)

    with pytest.raises(NodeNotFoundError):
        await CreateEdges(uow, POLICY).handle(
            CreateEdgesCommand(
                source_id=source.id, target_ids=[mine.id, theirs.id], type="owns"
            ),
            ALICE,
        )

    assert edges.writes == 0
    assert await _all(repos) == []
    assert await repos.edge_types.get_by_slug("owns") is None
    assert not uow.committed


async def test_create_edges_from_someone_elses_source_is_not_found() -> None:
    """A foreign source item is a 404 for the whole batch."""
    repos, edges = _repos()
    theirs = await _item(repos, BOB)
    mine = await _item(repos, ALICE)
    uow = InMemoryUnitOfWork(repos)

    with pytest.raises(NodeNotFoundError):
        await CreateEdges(uow, POLICY).handle(
            CreateEdgesCommand(source_id=theirs.id, target_ids=[mine.id], type="owns"),
            ALICE,
        )

    assert edges.writes == 0


async def test_create_edges_stamps_owner_and_ignores_foreign_existing_edges() -> None:
    """Created edges are owned by the actor; the duplicate check is scoped too."""
    repos, _ = _repos()
    source = await _item(repos, ALICE)
    target = await _item(repos, ALICE)
    uow = InMemoryUnitOfWork(repos)

    result = await CreateEdges(uow, POLICY).handle(
        CreateEdgesCommand(source_id=source.id, target_ids=[target.id], type="owns"),
        ALICE,
    )

    assert [e.owner_id for e in result.created] == [ALICE.id]
    assert uow.committed is True


async def _all(repos: GraphRepos) -> list[Edge]:
    return await repos.edges.list(scope=ContentFilter.everyone(), after=None, limit=50)


async def test_get_edge_is_not_found_for_someone_else() -> None:
    """Someone else's connection answers exactly like a missing one."""
    repos, _ = _repos()
    edge = await _connection(repos, ALICE)
    use_case = GetEdge(repos, POLICY)

    assert await use_case.handle(GetEdgeQuery(edge_id=edge.id), ALICE) is edge
    with pytest.raises(EdgeNotFoundError):
        await use_case.handle(GetEdgeQuery(edge_id=edge.id), BOB)


async def test_list_edges_returns_only_the_actors_connections() -> None:
    """The page, with or without a node filter, uses the actor's scope."""
    repos, _ = _repos()
    mine = await _connection(repos, ALICE)
    theirs = await _connection(repos, BOB)
    use_case = ListEdges(repos, POLICY)

    assert await use_case.handle(ListEdgesQuery(), ALICE) == [mine]
    assert await use_case.handle(ListEdgesQuery(), BOB) == [theirs]
    assert await use_case.handle(ListEdgesQuery(node_id=mine.source_id), BOB) == []
    assert await use_case.handle(ListEdgesQuery(node_id=mine.source_id), ALICE) == [
        mine
    ]


async def test_update_edge_is_not_found_for_someone_else() -> None:
    """Editing someone else's connection fails and changes nothing."""
    repos, edges = _repos()
    edge = await _connection(repos, ALICE, attributes={"k": "v"})
    edges.writes = 0
    uow = InMemoryUnitOfWork(repos)

    with pytest.raises(EdgeNotFoundError):
        await UpdateEdge(uow, POLICY).handle(
            UpdateEdgeCommand(edge_id=edge.id, attributes={"k": "stolen"}), BOB
        )

    assert edge.attributes == {"k": "v"}
    assert edges.writes == 0
    assert not uow.committed


async def test_delete_edge_is_not_found_for_someone_else() -> None:
    """Deleting someone else's connection fails and leaves it alive."""
    repos, edges = _repos()
    edge = await _connection(repos, ALICE)
    edges.writes = 0
    uow = InMemoryUnitOfWork(repos)

    with pytest.raises(EdgeNotFoundError):
        await DeleteEdge(uow, POLICY).handle(DeleteEdgeCommand(edge_id=edge.id), BOB)

    assert not edge.is_deleted
    assert edges.writes == 0
    assert not uow.committed


async def test_owner_can_update_and_delete_their_connection() -> None:
    """The happy path still works for the owner."""
    repos, _ = _repos()
    edge = await _connection(repos, ALICE, attributes={"k": "v"})

    updated = await UpdateEdge(InMemoryUnitOfWork(repos), POLICY).handle(
        UpdateEdgeCommand(edge_id=edge.id, attributes={"k": "w"}), ALICE
    )
    await DeleteEdge(InMemoryUnitOfWork(repos), POLICY).handle(
        DeleteEdgeCommand(edge_id=edge.id), ALICE
    )

    assert updated.attributes == {"k": "w"}
    assert edge.is_deleted


async def test_edge_type_usage_counts_use_the_viewers_scope() -> None:
    """Counts never include other people's connections."""
    repos, _ = _repos()
    edge_type = EdgeType.create(slug="owns", label="Owns")
    await repos.edge_types.add(edge_type)
    await _connection(repos, ALICE, "owns", attributes={"note": "x"})
    await _connection(repos, BOB, "owns", attributes={"note": "x"})
    await _connection(repos, BOB, "owns", attributes={"note": "y"})
    use_case = CountEdgeTypeAttributeUsage(repos, POLICY)
    query = CountEdgeTypeAttributeUsageQuery(edge_type_id=edge_type.id, key="note")

    assert await use_case.handle(query, ALICE) == 1
    assert await use_case.handle(query, BOB) == 2


async def test_use_cases_ask_the_policy_for_the_right_check() -> None:
    """Each path calls scope plus the matching assert, nothing else."""
    repos, _ = _repos()
    edge = await _connection(repos, ALICE, attributes={"k": "v"})

    async def calls(build: type, command: object, *, query: bool = False) -> list[str]:
        policy = _RecordingPolicy()
        arg = repos if query else InMemoryUnitOfWork(repos)
        await build(arg, policy).handle(command, ALICE)
        return policy.calls

    assert await calls(GetEdge, GetEdgeQuery(edge_id=edge.id), query=True) == [
        "scope",
        "view",
    ]
    assert await calls(
        UpdateEdge, UpdateEdgeCommand(edge_id=edge.id, attributes={"k": "w"})
    ) == ["scope", "modify"]
    assert await calls(DeleteEdge, DeleteEdgeCommand(edge_id=edge.id)) == [
        "scope",
        "delete",
    ]
