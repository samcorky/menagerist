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
from app.modules.graph.application.list_attribute_values import (
    AttributeValueCountResult,
    ListAttributeValues,
    ListAttributeValuesQuery,
)
from app.modules.graph.domain.errors import NodeTypeNotFoundError
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.actor import SYSTEM_ACTOR


def _repos() -> GraphRepos:
    return GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )


async def _setup() -> tuple[GraphRepos, NodeType]:
    repos = _repos()
    node_type = NodeType.create(slug="film", label="Film")
    await repos.node_types.add(node_type)
    nodes = [
        Node.create(name="A", type="film", attributes={"status": "Draft"}),
        Node.create(name="B", type="film", attributes={"status": "Draft"}),
        Node.create(name="C", type="film", attributes={"status": "Live"}),
        Node.create(name="D", type="film", attributes={"status": 1}),
        Node.create(name="E", type="film", attributes={}),
        Node.create(name="F", type="book", attributes={"status": "Draft"}),
    ]
    deleted = Node.create(name="G", type="film", attributes={"status": "Draft"})
    deleted.soft_delete()
    for node in [*nodes, deleted]:
        await repos.nodes.add(node)
    return repos, node_type


async def test_list_attribute_values_orders_by_count_then_value() -> None:
    """Values are most-used first, ties broken alphabetically; non-strings ignored."""
    repos, node_type = await _setup()

    values = await ListAttributeValues(repos).handle(
        ListAttributeValuesQuery(node_type_id=node_type.id, key="status"),
        SYSTEM_ACTOR,
    )

    assert values == [
        AttributeValueCountResult(value="Draft", count=2),
        AttributeValueCountResult(value="Live", count=1),
    ]


async def test_list_attribute_values_filters_by_q_case_insensitively() -> None:
    """`q` filters values by case-insensitive substring."""
    repos, node_type = await _setup()

    values = await ListAttributeValues(repos).handle(
        ListAttributeValuesQuery(node_type_id=node_type.id, key="status", q="live"),
        SYSTEM_ACTOR,
    )

    assert values == [AttributeValueCountResult(value="Live", count=1)]


async def test_list_attribute_values_respects_limit() -> None:
    """At most `limit` values are returned."""
    repos, node_type = await _setup()

    values = await ListAttributeValues(repos).handle(
        ListAttributeValuesQuery(node_type_id=node_type.id, key="status", limit=1),
        SYSTEM_ACTOR,
    )

    assert values == [AttributeValueCountResult(value="Draft", count=2)]


async def test_list_attribute_values_raises_for_missing_type() -> None:
    """An unknown node type id is a not-found error."""
    with pytest.raises(NodeTypeNotFoundError):
        await ListAttributeValues(_repos()).handle(
            ListAttributeValuesQuery(node_type_id=uuid.uuid4(), key="status"),
            SYSTEM_ACTOR,
        )
