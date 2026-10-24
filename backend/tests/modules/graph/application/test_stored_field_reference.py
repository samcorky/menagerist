"""A stored smart collection whose `ref` field later changes degrades, never errors."""

import uuid
from datetime import date
from typing import Any

import pytest

from app.modules.graph.adapters.persistence.in_memory_collection_members import (
    InMemoryCollectionMembers,
)
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
from app.modules.graph.application.list_nodes import ListNodes, ListNodesQuery
from app.modules.graph.application.prepare_query import count_matching, prepare_query
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.domain.query import InvalidQueryError
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import Actor
from app.shared_kernel.content_filter import ContentFilter

ALICE = uuid.UUID(int=1)
AS_ALICE = Actor(id=ALICE, roles=frozenset({"member"}))
TODAY = date(2026, 10, 24)
SCOPE = ContentFilter.of(ALICE)
NUMBER = {"type": "number", "x-menagerist": {"kind": "number"}}
DEFINITION: dict[str, Any] = {
    "v": 1,
    "where": {
        "op": "and",
        "children": [
            {
                "kind": "field",
                "type": "part",
                "key": "in_stock",
                "op": "<=",
                "value": {"ref": "reorder_at"},
            }
        ],
    },
}


def _schema(**properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": properties}


class World:
    """One `part` type with a low item, over in-memory repositories."""

    def __init__(self, schema: dict[str, Any]) -> None:
        self.repos = GraphRepos(
            nodes=InMemoryNodeRepository(),
            edges=InMemoryEdgeRepository(),
            node_types=InMemoryNodeTypeRepository(),
            edge_types=InMemoryEdgeTypeRepository(),
        )
        self.members = InMemoryCollectionMembers()
        self.id = uuid.uuid7()
        self.members.add_smart_collection(self.id, DEFINITION, owner_id=ALICE)
        self.schema = schema

    async def setup(self) -> None:
        """Add the type and one item that is at its reorder level."""
        await self.repos.node_types.add(
            NodeType.create(slug="part", label="Part", attributes_schema=self.schema)
        )
        await self.repos.nodes.add(
            Node.create(
                owner_id=ALICE,
                name="LM317",
                type="part",
                attributes={"in_stock": 3, "reorder_at": 5},
            )
        )

    async def listed(self) -> list[str]:
        """Names the stored collection lists."""
        use_case = ListNodes(
            self.repos, InMemoryAccessGuard(), self.members, today=lambda: TODAY
        )
        result = await use_case.handle(ListNodesQuery(collection=self.id), AS_ALICE)
        return [n.name for n in result.items]


async def _world(schema: dict[str, Any]) -> World:
    world = World(schema)
    await world.setup()
    return world


async def test_the_reference_matches_while_both_fields_exist() -> None:
    """Baseline: the rule lists the part at or under its own reorder level."""
    world = await _world(_schema(in_stock=NUMBER, reorder_at=NUMBER))

    assert await world.listed() == ["LM317"]


async def test_a_removed_referenced_field_warns_and_lists_nothing() -> None:
    """The `ref` target is gone: a warning on the condition, no match, no error."""
    world = await _world(_schema(in_stock=NUMBER))

    resolved, warnings = await prepare_query(
        world.repos, DEFINITION, TODAY, scope=SCOPE
    )

    assert [w.path for w in warnings] == ["where.children[0]"]
    assert resolved.stale
    assert await world.listed() == []
    assert await count_matching(world.repos, DEFINITION, SCOPE, cap=None) == (0, False)


@pytest.mark.parametrize(
    "schema",
    [
        _schema(in_stock=NUMBER, reorder_at={"type": "string"}),
        _schema(
            in_stock=NUMBER,
            reorder_at={"type": "number", "x-menagerist": {"kind": "rating"}},
        ),
        _schema(in_stock={"type": "string"}, reorder_at=NUMBER),
        _schema(in_stock={"type": "boolean"}, reorder_at={"type": "boolean"}),
    ],
    ids=["ref-to-text", "ref-to-rating", "field-to-text", "both-non-comparable"],
)
async def test_a_changed_field_kind_makes_the_stored_query_unreadable(
    schema: dict[str, Any],
) -> None:
    """`prepare_query` refuses it (as for any operator that stops fitting).

    Every place that evaluates a stored definition catches that and lists nothing.
    """
    world = await _world(schema)

    with pytest.raises(InvalidQueryError):
        await prepare_query(world.repos, DEFINITION, TODAY, scope=SCOPE)
    assert await world.listed() == []
