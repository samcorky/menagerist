"""Deleting a type and purging an attribute rewrite everyone's content: admin only."""

import uuid

import pytest

from app.entrypoints.api.shared.access_policy import OwnerAccessPolicy
from app.entrypoints.api.shared.authorization import RoleAuthorizationAdapter
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
from app.modules.graph.application.delete_edge_type import (
    DeleteEdgeType,
    DeleteEdgeTypeCommand,
)
from app.modules.graph.application.delete_node_type import (
    DeleteNodeType,
    DeleteNodeTypeCommand,
)
from app.modules.graph.application.purge_edge_type_attribute import (
    PurgeEdgeTypeAttribute,
    PurgeEdgeTypeAttributeCommand,
)
from app.modules.graph.application.purge_node_type_attribute import (
    PurgeNodeTypeAttribute,
    PurgeNodeTypeAttributeCommand,
)
from app.modules.graph.domain.edge import Edge
from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.domain.errors import EdgeTypeInUseError
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.actor import Actor
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.errors import ForbiddenError
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

ADMIN = Actor(id=uuid.UUID(int=100), roles=frozenset({"admin"}))
ALICE = Actor(id=uuid.UUID(int=101), roles=frozenset({"member"}))
BOB = Actor(id=uuid.UUID(int=102), roles=frozenset({"member"}))
POLICY = OwnerAccessPolicy()
ALL = ContentFilter.everyone()


def _repos() -> GraphRepos:
    return GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )


async def _items_of_two_people(repos: GraphRepos) -> tuple[NodeType, list[Node]]:
    node_type = NodeType.create(slug="film", label="Film")
    await repos.node_types.add(node_type)
    nodes = [
        Node.create(
            owner_id=owner.id,
            name=owner.id.hex,
            type="film",
            attributes={"rating": "PG", "keep": "me"},
        )
        for owner in (ALICE, BOB)
    ]
    for node in nodes:
        await repos.nodes.add(node)
    return node_type, nodes


async def _connections_of_two_people(
    repos: GraphRepos, *, attributes: dict[str, str]
) -> tuple[EdgeType, list[Edge]]:
    edge_type = EdgeType.create(slug="owns", label="Owns")
    await repos.edge_types.add(edge_type)
    edges = []
    for owner in (ALICE, BOB):
        source = Node.create(owner_id=owner.id, name="a")
        target = Node.create(owner_id=owner.id, name="b")
        await repos.nodes.add(source)
        await repos.nodes.add(target)
        edge = Edge.create(
            owner_id=owner.id,
            source_id=source.id,
            target_id=target.id,
            type="owns",
            attributes=dict(attributes),
        )
        await repos.edges.add(edge)
        edges.append(edge)
    return edge_type, edges


async def test_member_cannot_delete_a_node_type() -> None:
    """A member gets 403 and nothing changes."""
    repos = _repos()
    node_type, nodes = await _items_of_two_people(repos)
    uow = InMemoryUnitOfWork(repos)

    with pytest.raises(ForbiddenError):
        await DeleteNodeType(uow, RoleAuthorizationAdapter()).handle(
            DeleteNodeTypeCommand(node_type_id=node_type.id), ALICE
        )

    assert not node_type.is_deleted
    assert [n.type for n in nodes] == ["film", "film"]
    assert not uow.committed


async def test_admin_deleting_a_node_type_clears_everyones_items() -> None:
    """The type is cleared on every person's items, not only the admin's."""
    repos = _repos()
    node_type, nodes = await _items_of_two_people(repos)
    uow = InMemoryUnitOfWork(repos)

    await DeleteNodeType(uow, RoleAuthorizationAdapter()).handle(
        DeleteNodeTypeCommand(node_type_id=node_type.id), ADMIN
    )

    assert node_type.is_deleted
    assert [n.type for n in nodes] == [None, None]
    assert uow.committed


async def test_member_cannot_purge_a_node_type_attribute() -> None:
    """A member gets 403 and no item is touched."""
    repos = _repos()
    node_type, nodes = await _items_of_two_people(repos)
    uow = InMemoryUnitOfWork(repos)

    with pytest.raises(ForbiddenError):
        await PurgeNodeTypeAttribute(uow, RoleAuthorizationAdapter()).handle(
            PurgeNodeTypeAttributeCommand(node_type_id=node_type.id, key="rating"),
            BOB,
        )

    assert all("rating" in n.attributes for n in nodes)
    assert not uow.committed


async def test_admin_purging_a_node_type_attribute_spans_everyones_items() -> None:
    """The key is removed from every person's items."""
    repos = _repos()
    node_type, nodes = await _items_of_two_people(repos)
    uow = InMemoryUnitOfWork(repos)

    await PurgeNodeTypeAttribute(uow, RoleAuthorizationAdapter()).handle(
        PurgeNodeTypeAttributeCommand(node_type_id=node_type.id, key="rating"), ADMIN
    )
    assert [n.attributes for n in nodes] == [{"keep": "me"}, {"keep": "me"}]


async def test_member_cannot_delete_an_edge_type() -> None:
    """A member gets 403, even for a type no connection uses."""
    repos = _repos()
    edge_type = EdgeType.create(slug="owns", label="Owns")
    await repos.edge_types.add(edge_type)
    uow = InMemoryUnitOfWork(repos)

    with pytest.raises(ForbiddenError):
        await DeleteEdgeType(uow, RoleAuthorizationAdapter()).handle(
            DeleteEdgeTypeCommand(edge_type_id=edge_type.id), ALICE
        )

    assert not edge_type.is_deleted
    assert not uow.committed


async def test_admin_edge_type_delete_sees_everyones_connections() -> None:
    """The in-use check spans all users: another person's connection blocks it."""
    repos = _repos()
    edge_type = EdgeType.create(slug="owns", label="Owns")
    await repos.edge_types.add(edge_type)
    source = Node.create(owner_id=ALICE.id, name="a")
    target = Node.create(owner_id=ALICE.id, name="b")
    await repos.nodes.add(source)
    await repos.nodes.add(target)
    await repos.edges.add(
        Edge.create(
            owner_id=ALICE.id, source_id=source.id, target_id=target.id, type="owns"
        )
    )
    uow = InMemoryUnitOfWork(repos)

    with pytest.raises(EdgeTypeInUseError):
        await DeleteEdgeType(uow, RoleAuthorizationAdapter()).handle(
            DeleteEdgeTypeCommand(edge_type_id=edge_type.id), ADMIN
        )

    assert not edge_type.is_deleted


async def test_admin_can_delete_an_unused_edge_type() -> None:
    """With no connection from anyone, the admin's delete goes through."""
    repos = _repos()
    edge_type = EdgeType.create(slug="owns", label="Owns")
    await repos.edge_types.add(edge_type)
    uow = InMemoryUnitOfWork(repos)

    await DeleteEdgeType(uow, RoleAuthorizationAdapter()).handle(
        DeleteEdgeTypeCommand(edge_type_id=edge_type.id), ADMIN
    )

    assert edge_type.is_deleted
    assert uow.committed


async def test_member_cannot_purge_an_edge_type_attribute() -> None:
    """A member gets 403 and no connection is touched."""
    repos = _repos()
    edge_type, edges = await _connections_of_two_people(repos, attributes={"n": "1"})
    uow = InMemoryUnitOfWork(repos)

    with pytest.raises(ForbiddenError):
        await PurgeEdgeTypeAttribute(uow, RoleAuthorizationAdapter()).handle(
            PurgeEdgeTypeAttributeCommand(edge_type_id=edge_type.id, key="n"), ALICE
        )

    assert all(e.attributes == {"n": "1"} for e in edges)
    assert not uow.committed


async def test_admin_purging_an_edge_type_attribute_spans_everyones_connections() -> (
    None
):
    """The key is removed from every person's connections."""
    repos = _repos()
    edge_type, edges = await _connections_of_two_people(repos, attributes={"n": "1"})
    uow = InMemoryUnitOfWork(repos)

    await PurgeEdgeTypeAttribute(uow, RoleAuthorizationAdapter()).handle(
        PurgeEdgeTypeAttributeCommand(edge_type_id=edge_type.id, key="n"), ADMIN
    )
    assert [e.attributes for e in edges] == [{}, {}]
