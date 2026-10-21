"""Item use cases with two people: ownership is stamped and enforced."""

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
from app.modules.graph.application.count_node_type_attribute_usage import (
    CountNodeTypeAttributeUsage,
    CountNodeTypeAttributeUsageQuery,
)
from app.modules.graph.application.create_node import CreateNode, CreateNodeCommand
from app.modules.graph.application.delete_node import DeleteNode, DeleteNodeCommand
from app.modules.graph.application.get_node import GetNode, GetNodeQuery
from app.modules.graph.application.list_attribute_values import (
    AttributeValueCountResult,
    ListAttributeValues,
    ListAttributeValuesQuery,
)
from app.modules.graph.application.list_nodes import ListNodes, ListNodesQuery
from app.modules.graph.application.promote_extra_schema_field import (
    PromoteExtraSchemaField,
    PromoteExtraSchemaFieldCommand,
)
from app.modules.graph.application.update_node import UpdateNode, UpdateNodeCommand
from app.modules.graph.domain.errors import NodeNotFoundError
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.actor import Actor
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

if TYPE_CHECKING:
    from app.shared_kernel.access_policy import AccessPolicy

ALICE = Actor(id=uuid.UUID(int=101), roles=frozenset({"member"}))
BOB = Actor(id=uuid.UUID(int=102), roles=frozenset({"member"}))
POLICY = OwnerAccessPolicy()


def _repos() -> GraphRepos:
    return GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )


class _RecordingPolicy:
    """Wraps the real policy and records which check each use case asks for."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self._inner = OwnerAccessPolicy()

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


async def _alices_item(repos: GraphRepos, **kwargs: Any) -> Node:  # noqa: ANN401
    node = Node.create(owner_id=ALICE.id, name="Alien", **kwargs)
    await repos.nodes.add(node)
    return node


async def test_create_node_stamps_the_actor_as_owner() -> None:
    """The creator owns the new item; only they can then see it."""
    repos = _repos()
    uow = InMemoryUnitOfWork(repos)

    node = await CreateNode(uow, POLICY).handle(CreateNodeCommand(name="Alien"), ALICE)

    assert uow.committed is True

    assert node.owner_id == ALICE.id
    assert await repos.nodes.get(node.id, scope=ContentFilter.of(ALICE.id)) is node
    assert await repos.nodes.get(node.id, scope=ContentFilter.of(BOB.id)) is None


async def test_get_node_is_not_found_for_someone_else() -> None:
    """Someone else's item answers exactly like a missing one."""
    repos = _repos()
    node = await _alices_item(repos)
    use_case = GetNode(repos, POLICY)

    assert await use_case.handle(GetNodeQuery(node_id=node.id), ALICE) is node
    with pytest.raises(NodeNotFoundError):
        await use_case.handle(GetNodeQuery(node_id=node.id), BOB)


async def test_list_nodes_returns_only_the_actors_items_and_total() -> None:
    """The page and the total both use the actor's scope."""
    repos = _repos()
    mine = await _alices_item(repos)
    await repos.nodes.add(Node.create(owner_id=BOB.id, name="Blade Runner"))
    use_case = ListNodes(repos, POLICY)

    alice = await use_case.handle(ListNodesQuery(), ALICE)
    bob = await use_case.handle(ListNodesQuery(q="blade"), BOB)
    nobody = await use_case.handle(ListNodesQuery(q="alien"), BOB)

    assert alice.items == [mine]
    assert alice.total == 1
    assert [n.name for n in bob.items] == ["Blade Runner"]
    assert bob.total == 1
    assert nobody.items == []
    assert nobody.total == 0


async def test_update_node_is_not_found_for_someone_else() -> None:
    """Editing someone else's item fails and changes nothing."""
    repos = _repos()
    node = await _alices_item(repos)
    uow = InMemoryUnitOfWork(repos)

    with pytest.raises(NodeNotFoundError):
        await UpdateNode(uow, POLICY).handle(
            UpdateNodeCommand(node_id=node.id, name="Stolen"), BOB
        )

    assert node.name == "Alien"
    assert not uow.committed


async def test_delete_node_is_not_found_for_someone_else() -> None:
    """Deleting someone else's item fails and leaves it alive."""
    repos = _repos()
    node = await _alices_item(repos)
    uow = InMemoryUnitOfWork(repos)

    with pytest.raises(NodeNotFoundError):
        await DeleteNode(uow, POLICY).handle(DeleteNodeCommand(node_id=node.id), BOB)

    assert not node.is_deleted
    assert not uow.committed


async def test_promote_is_not_found_for_someone_else() -> None:
    """Promoting a field on someone else's item fails."""
    repos = _repos()
    node = await _alices_item(
        repos, extra_schema={"properties": {"x": {"type": "string"}}}
    )
    node_type = NodeType.create(slug="film", label="Film")
    await repos.node_types.add(node_type)
    uow = InMemoryUnitOfWork(repos)

    with pytest.raises(NodeNotFoundError):
        await PromoteExtraSchemaField(uow, POLICY).handle(
            PromoteExtraSchemaFieldCommand(
                node_id=node.id, node_type_id=node_type.id, key="x"
            ),
            BOB,
        )

    assert not uow.committed


async def test_usage_counts_and_value_suggestions_use_the_viewers_scope() -> None:
    """Counts and suggestions never include other people's items."""
    repos = _repos()
    node_type = NodeType.create(slug="film", label="Film")
    await repos.node_types.add(node_type)
    await _alices_item(repos, type="film", attributes={"rating": "PG"})
    await repos.nodes.add(
        Node.create(
            owner_id=BOB.id, name="Other", type="film", attributes={"rating": "R"}
        )
    )

    usage = CountNodeTypeAttributeUsage(repos, POLICY)
    values = ListAttributeValues(repos, POLICY)
    usage_query = CountNodeTypeAttributeUsageQuery(
        node_type_id=node_type.id, key="rating"
    )
    values_query = ListAttributeValuesQuery(node_type_id=node_type.id, key="rating")

    assert await usage.handle(usage_query, ALICE) == 1
    assert await usage.handle(usage_query, BOB) == 1
    assert await values.handle(values_query, ALICE) == [
        AttributeValueCountResult(value="PG", count=1)
    ]
    assert await values.handle(values_query, BOB) == [
        AttributeValueCountResult(value="R", count=1)
    ]


async def test_each_use_case_asks_the_policy_for_the_right_check() -> None:
    """Reads ask for view, edits for modify and deletes for delete."""
    repos = _repos()
    node = await _alices_item(repos)
    uow = InMemoryUnitOfWork(repos)
    recorder = _RecordingPolicy()
    policy: AccessPolicy = recorder

    await GetNode(repos, policy).handle(GetNodeQuery(node_id=node.id), ALICE)
    assert recorder.calls == ["scope", "view"]

    recorder.calls.clear()
    await UpdateNode(uow, policy).handle(
        UpdateNodeCommand(node_id=node.id, name="Aliens"), ALICE
    )
    assert recorder.calls == ["scope", "modify"]

    recorder.calls.clear()
    await ListNodes(repos, policy).handle(ListNodesQuery(), ALICE)
    assert recorder.calls == ["scope"]

    recorder.calls.clear()
    await DeleteNode(uow, policy).handle(DeleteNodeCommand(node_id=node.id), ALICE)
    assert recorder.calls == ["scope", "delete"]
