"""Deleting a type and purging an attribute reach only the owner's own content."""

import uuid

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
from app.modules.graph.domain.errors import (
    EdgeTypeInUseError,
    EdgeTypeNotFoundError,
    NodeTypeNotFoundError,
)
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.actor import Actor
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

ADMIN = Actor(id=uuid.UUID(int=100), roles=frozenset({"admin"}))
ALICE = Actor(id=uuid.UUID(int=101), roles=frozenset({"member"}))
BOB = Actor(id=uuid.UUID(int=102), roles=frozenset({"member"}))


def _repos() -> GraphRepos:
    return GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )


async def _item_types_with_items(
    repos: GraphRepos,
) -> tuple[dict[uuid.UUID, NodeType], dict[uuid.UUID, Node]]:
    """Alice and Bob each own a `film` type and one item of it."""
    types: dict[uuid.UUID, NodeType] = {}
    nodes: dict[uuid.UUID, Node] = {}
    for person in (ALICE, BOB):
        types[person.id] = NodeType.create(owner_id=person.id, slug="film", label="F")
        nodes[person.id] = Node.create(
            owner_id=person.id,
            name=person.id.hex,
            type="film",
            attributes={"rating": "PG", "keep": "me"},
        )
        await repos.node_types.add(types[person.id])
        await repos.nodes.add(nodes[person.id])
    return types, nodes


async def _relationship_types_with_connections(
    repos: GraphRepos, *, attributes: dict[str, str]
) -> tuple[dict[uuid.UUID, EdgeType], dict[uuid.UUID, Edge]]:
    """Alice and Bob each own an `owns` type and one connection of it."""
    types: dict[uuid.UUID, EdgeType] = {}
    edges: dict[uuid.UUID, Edge] = {}
    for person in (ALICE, BOB):
        types[person.id] = EdgeType.create(owner_id=person.id, slug="owns", label="O")
        source = Node.create(owner_id=person.id, name="a")
        target = Node.create(owner_id=person.id, name="b")
        edges[person.id] = Edge.create(
            owner_id=person.id,
            source_id=source.id,
            target_id=target.id,
            type="owns",
            attributes=dict(attributes),
        )
        await repos.edge_types.add(types[person.id])
        for node in (source, target):
            await repos.nodes.add(node)
        await repos.edges.add(edges[person.id])
    return types, edges


async def test_an_owner_deletes_their_type_and_clears_only_their_items() -> None:
    """Bob keeps his own `film` type and item when Alice deletes hers."""
    repos = _repos()
    types, nodes = await _item_types_with_items(repos)
    uow = InMemoryUnitOfWork(repos)

    await DeleteNodeType(uow, get_access_guard()).handle(
        DeleteNodeTypeCommand(node_type_id=types[ALICE.id].id), ALICE
    )

    assert types[ALICE.id].is_deleted
    assert nodes[ALICE.id].type is None
    assert not types[BOB.id].is_deleted
    assert nodes[BOB.id].type == "film"
    assert uow.committed


@pytest.mark.parametrize("stranger", [BOB, ADMIN], ids=["member", "admin"])
async def test_nobody_else_can_delete_a_node_type(stranger: Actor) -> None:
    """Another person's type reads as missing, whatever the stranger's role."""
    repos = _repos()
    types, nodes = await _item_types_with_items(repos)
    uow = InMemoryUnitOfWork(repos)

    with pytest.raises(NodeTypeNotFoundError):
        await DeleteNodeType(uow, get_access_guard()).handle(
            DeleteNodeTypeCommand(node_type_id=types[ALICE.id].id), stranger
        )

    assert not types[ALICE.id].is_deleted
    assert nodes[ALICE.id].type == "film"
    assert not uow.committed


async def test_an_owner_purges_an_attribute_from_only_their_items() -> None:
    """The key goes from Alice's items and stays on Bob's."""
    repos = _repos()
    types, nodes = await _item_types_with_items(repos)
    uow = InMemoryUnitOfWork(repos)

    await PurgeNodeTypeAttribute(uow, get_access_guard()).handle(
        PurgeNodeTypeAttributeCommand(node_type_id=types[ALICE.id].id, key="rating"),
        ALICE,
    )

    assert nodes[ALICE.id].attributes == {"keep": "me"}
    assert nodes[BOB.id].attributes == {"rating": "PG", "keep": "me"}


async def test_nobody_else_can_purge_an_attribute() -> None:
    """Bob cannot purge Alice's type; no item is touched."""
    repos = _repos()
    types, nodes = await _item_types_with_items(repos)
    uow = InMemoryUnitOfWork(repos)

    with pytest.raises(NodeTypeNotFoundError):
        await PurgeNodeTypeAttribute(uow, get_access_guard()).handle(
            PurgeNodeTypeAttributeCommand(
                node_type_id=types[ALICE.id].id, key="rating"
            ),
            BOB,
        )

    assert all("rating" in n.attributes for n in nodes.values())
    assert not uow.committed


async def test_a_relationship_type_is_blocked_only_by_its_owners_connections() -> None:
    """Bob's connection of the same slug does not stop Alice; her own does."""
    repos = _repos()
    types, edges = await _relationship_types_with_connections(repos, attributes={})
    uow = InMemoryUnitOfWork(repos)

    with pytest.raises(EdgeTypeInUseError):
        await DeleteEdgeType(uow, get_access_guard()).handle(
            DeleteEdgeTypeCommand(edge_type_id=types[ALICE.id].id), ALICE
        )

    edges[ALICE.id].soft_delete()
    await DeleteEdgeType(uow, get_access_guard()).handle(
        DeleteEdgeTypeCommand(edge_type_id=types[ALICE.id].id), ALICE
    )

    assert types[ALICE.id].is_deleted
    assert not types[BOB.id].is_deleted


async def test_nobody_else_can_delete_a_relationship_type() -> None:
    """Another person's relationship type reads as missing."""
    repos = _repos()
    types, _ = await _relationship_types_with_connections(repos, attributes={})
    uow = InMemoryUnitOfWork(repos)

    with pytest.raises(EdgeTypeNotFoundError):
        await DeleteEdgeType(uow, get_access_guard()).handle(
            DeleteEdgeTypeCommand(edge_type_id=types[ALICE.id].id), ADMIN
        )

    assert not types[ALICE.id].is_deleted


async def test_an_owner_purges_a_relationship_attribute_from_their_own_only() -> None:
    """The key goes from Alice's connections and stays on Bob's."""
    repos = _repos()
    types, edges = await _relationship_types_with_connections(
        repos, attributes={"n": "1"}
    )
    uow = InMemoryUnitOfWork(repos)

    await PurgeEdgeTypeAttribute(uow, get_access_guard()).handle(
        PurgeEdgeTypeAttributeCommand(edge_type_id=types[ALICE.id].id, key="n"), ALICE
    )

    assert edges[ALICE.id].attributes == {}
    assert edges[BOB.id].attributes == {"n": "1"}


async def test_nobody_else_can_purge_a_relationship_attribute() -> None:
    """Bob cannot purge Alice's relationship type."""
    repos = _repos()
    types, edges = await _relationship_types_with_connections(
        repos, attributes={"n": "1"}
    )
    uow = InMemoryUnitOfWork(repos)

    with pytest.raises(EdgeTypeNotFoundError):
        await PurgeEdgeTypeAttribute(uow, get_access_guard()).handle(
            PurgeEdgeTypeAttributeCommand(edge_type_id=types[ALICE.id].id, key="n"),
            BOB,
        )

    assert all(e.attributes == {"n": "1"} for e in edges.values())
    assert not uow.committed
