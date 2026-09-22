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
from app.modules.graph.application.promote_extra_schema_field import (
    PromoteExtraSchemaField,
    PromoteExtraSchemaFieldCommand,
)
from app.modules.graph.domain.errors import (
    InvalidSchemaError,
    NodeNotFoundError,
    NodeTypeNotFoundError,
)
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork


def _repos(
    nodes: InMemoryNodeRepository | None = None,
    node_types: InMemoryNodeTypeRepository | None = None,
) -> GraphRepos:
    """Build a `GraphRepos` bundle for tests, with in-memory repos by default."""
    return GraphRepos(
        nodes=nodes or InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=node_types or InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )


async def test_moves_the_property_and_keeps_the_value() -> None:
    """Promoting a field adds it to the type schema and keeps its attribute value."""
    node_type = NodeType.create(
        slug="film",
        label="Film",
        attributes_schema={
            "type": "object",
            "properties": {"title": {"title": "Title", "type": "string"}},
        },
    )
    node_types = InMemoryNodeTypeRepository()
    await node_types.add(node_type)

    node = Node.create(
        name="Alien",
        type="film",
        attributes={"title": "Alien", "condition": "Mint"},
        extra_schema={
            "type": "object",
            "properties": {"condition": {"title": "Condition", "type": "string"}},
        },
    )
    nodes = InMemoryNodeRepository()
    await nodes.add(node)

    repos = _repos(nodes=nodes, node_types=node_types)
    uow = InMemoryUnitOfWork(repos)
    command = PromoteExtraSchemaFieldCommand(
        node_id=node.id, node_type_id=node_type.id, key="condition"
    )

    updated = await PromoteExtraSchemaField(uow).handle(command, SYSTEM_ACTOR)

    assert updated.attributes["condition"] == "Mint"
    # Node.update()'s extra_schema convention treats None as "unchanged" (there
    # is no way to clear it via that command yet), so an overlay left with no
    # properties is represented as an empty properties dict, not None.
    assert updated.extra_schema is not None
    assert updated.extra_schema["properties"] == {}
    saved_type = await node_types.get(node_type.id)
    assert saved_type is not None
    assert saved_type.attributes_schema is not None
    assert "condition" in saved_type.attributes_schema["properties"]
    assert uow.committed


async def test_moves_one_property_and_keeps_the_others_in_the_overlay() -> None:
    """Promoting one field leaves the rest of the overlay untouched."""
    node_type = NodeType.create(slug="film", label="Film")
    node_types = InMemoryNodeTypeRepository()
    await node_types.add(node_type)

    node = Node.create(
        name="Alien",
        type="film",
        attributes={"condition": "Mint", "signed": True},
        extra_schema={
            "type": "object",
            "properties": {
                "condition": {"title": "Condition", "type": "string"},
                "signed": {"title": "Signed", "type": "boolean"},
            },
        },
    )
    nodes = InMemoryNodeRepository()
    await nodes.add(node)

    repos = _repos(nodes=nodes, node_types=node_types)
    uow = InMemoryUnitOfWork(repos)
    command = PromoteExtraSchemaFieldCommand(
        node_id=node.id, node_type_id=node_type.id, key="condition"
    )

    updated = await PromoteExtraSchemaField(uow).handle(command, SYSTEM_ACTOR)

    assert updated.extra_schema is not None
    assert "condition" not in updated.extra_schema["properties"]
    assert "signed" in updated.extra_schema["properties"]
    saved_type = await node_types.get(node_type.id)
    assert saved_type is not None
    assert saved_type.attributes_schema is not None
    assert "condition" in saved_type.attributes_schema["properties"]


async def test_key_not_in_the_overlay_raises() -> None:
    """Promoting a key absent from the node's overlay raises."""
    node_type = NodeType.create(slug="film", label="Film")
    node_types = InMemoryNodeTypeRepository()
    await node_types.add(node_type)
    node = Node.create(name="Alien", type="film")
    nodes = InMemoryNodeRepository()
    await nodes.add(node)
    uow = InMemoryUnitOfWork(_repos(nodes=nodes, node_types=node_types))

    with pytest.raises(InvalidSchemaError):
        await PromoteExtraSchemaField(uow).handle(
            PromoteExtraSchemaFieldCommand(
                node_id=node.id, node_type_id=node_type.id, key="condition"
            ),
            SYSTEM_ACTOR,
        )


async def test_key_already_on_the_type_raises() -> None:
    """Promoting a key that already exists on the item type raises."""
    node_type = NodeType.create(
        slug="film",
        label="Film",
        attributes_schema={
            "type": "object",
            "properties": {"condition": {"title": "Condition", "type": "string"}},
        },
    )
    node_types = InMemoryNodeTypeRepository()
    await node_types.add(node_type)
    node = Node.create(
        name="Alien",
        type="film",
        attributes={"condition": "Mint"},
        extra_schema={
            "type": "object",
            "properties": {"condition": {"title": "Condition", "type": "string"}},
        },
    )
    nodes = InMemoryNodeRepository()
    await nodes.add(node)
    uow = InMemoryUnitOfWork(_repos(nodes=nodes, node_types=node_types))

    with pytest.raises(InvalidSchemaError):
        await PromoteExtraSchemaField(uow).handle(
            PromoteExtraSchemaFieldCommand(
                node_id=node.id, node_type_id=node_type.id, key="condition"
            ),
            SYSTEM_ACTOR,
        )


async def test_node_not_found_raises() -> None:
    """Promoting a field on a missing node raises."""
    node_type = NodeType.create(slug="film", label="Film")
    node_types = InMemoryNodeTypeRepository()
    await node_types.add(node_type)
    uow = InMemoryUnitOfWork(_repos(node_types=node_types))

    with pytest.raises(NodeNotFoundError):
        await PromoteExtraSchemaField(uow).handle(
            PromoteExtraSchemaFieldCommand(
                node_id=uuid.uuid7(), node_type_id=node_type.id, key="condition"
            ),
            SYSTEM_ACTOR,
        )


async def test_node_type_not_found_raises() -> None:
    """Promoting a field onto a missing item type raises."""
    node = Node.create(
        name="Alien",
        type="film",
        extra_schema={
            "type": "object",
            "properties": {"condition": {"title": "Condition", "type": "string"}},
        },
    )
    nodes = InMemoryNodeRepository()
    await nodes.add(node)
    uow = InMemoryUnitOfWork(_repos(nodes=nodes))

    with pytest.raises(NodeTypeNotFoundError):
        await PromoteExtraSchemaField(uow).handle(
            PromoteExtraSchemaFieldCommand(
                node_id=node.id, node_type_id=uuid.uuid7(), key="condition"
            ),
            SYSTEM_ACTOR,
        )
