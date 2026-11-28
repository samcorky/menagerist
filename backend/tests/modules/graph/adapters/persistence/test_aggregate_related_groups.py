"""Grouping by a related item: one table of scenarios, both adapters.

The in-memory evaluator is the reference; the Postgres run joins `edges` in a
lateral select. The world has an item with two makers, a maker that is deleted,
one that is another person's, a deleted connection and a relationship with no
direction.
"""

import uuid
from datetime import date
from typing import TYPE_CHECKING, Any

import pytest

from app.entrypoints.api.shared.bridges.collection_conditions import (
    build_search_graph_repos,
)
from app.modules.graph.adapters.persistence.unit_of_work import (
    build_in_memory_graph_repos,
)
from app.modules.graph.application.aggregate_nodes import (
    AggregateNodes,
    AggregateNodesQuery,
    AggregateNodesResult,
)
from app.modules.graph.domain.aggregate import CurrencyValue, MeasureValue
from app.modules.graph.domain.edge import Edge
from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import Actor

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.modules.graph.ports.unit_of_work import GraphRepos

ALICE = Actor(id=uuid.UUID(int=901), roles=frozenset({"member"}))
BOB = uuid.UUID(int=902)

_FILM = {
    "type": "object",
    "properties": {"price": {"type": "object", "x-menagerist": {"kind": "money"}}},
}

# name -> (owner, type, price, deleted)
ITEMS: dict[str, tuple[uuid.UUID, str, float | None, bool]] = {
    "f1": (ALICE.id, "film", 10, False),
    "f2": (ALICE.id, "film", 5, False),
    "f3": (ALICE.id, "film", 2, False),
    "f4": (ALICE.id, "film", 1, False),
    "Acme": (ALICE.id, "maker", None, False),
    "Zeta": (ALICE.id, "maker", None, False),
    "Ghost": (ALICE.id, "maker", None, True),
    "Bobco": (BOB, "maker", None, False),
    "b1": (ALICE.id, "book", None, False),
}
IDS = {name: uuid.UUID(int=0x7000 + i) for i, name in enumerate(ITEMS)}
NAMES = {str(v): k for k, v in IDS.items()}

# source, target, relationship, deleted
EDGES: list[tuple[str, str, str, bool]] = [
    ("f1", "Acme", "made-by", False),
    ("f2", "Acme", "made-by", False),
    ("f2", "Zeta", "made-by", False),
    ("f3", "Ghost", "made-by", False),
    ("f4", "Bobco", "made-by", False),
    ("f1", "Zeta", "made-by", True),
    ("f1", "f2", "sequel", False),
]


async def _seed(repos: GraphRepos) -> AggregateNodes:
    for slug, schema in (("film", _FILM), ("maker", None), ("book", None)):
        await repos.node_types.add(
            NodeType.create(
                owner_id=ALICE.id,
                slug=slug,
                label=slug.title(),
                attributes_schema=schema,
            )
        )
    await repos.edge_types.add(
        EdgeType.create(owner_id=ALICE.id, slug="made-by", label="Made by")
    )
    await repos.edge_types.add(
        EdgeType.create(
            owner_id=ALICE.id, slug="sequel", label="Sequel", directional=False
        )
    )
    for name, (owner, type_slug, price, deleted) in ITEMS.items():
        node = Node.create(
            owner_id=owner,
            name=name,
            type=type_slug,
            attributes={}
            if price is None
            else {"price": {"value": price, "currency": "GBP"}},
        )
        node.id = IDS[name]
        if deleted:
            node.soft_delete()
        await repos.nodes.add(node)
    for source, target, relationship, deleted in EDGES:
        edge = Edge.create(
            owner_id=ALICE.id if target != "Bobco" else BOB,
            source_id=IDS[source],
            target_id=IDS[target],
            type=relationship,
        )
        if deleted:
            edge.soft_delete()
        await repos.edges.add(edge)
    return AggregateNodes(
        repos, InMemoryAccessGuard(), today=lambda: date(2026, 11, 28)
    )


@pytest.fixture(
    params=["in_memory", pytest.param("postgres", marks=pytest.mark.integration)]
)
def world(request: pytest.FixtureRequest) -> Callable[[], Awaitable[AggregateNodes]]:
    """Seeds the same world on either adapter; awaiting it gives the use case."""
    session = (
        None if request.param == "in_memory" else request.getfixturevalue("db_session")
    )

    async def build() -> AggregateNodes:
        repos = (
            build_in_memory_graph_repos()
            if session is None
            else build_search_graph_repos(session)
        )
        return await _seed(repos)

    return build


_PRICE = {"fn": "sum", "type": "film", "key": "price"}


async def _run(
    use_case: AggregateNodes, group_by: dict[str, Any]
) -> AggregateNodesResult:
    return await use_case.handle(
        AggregateNodesQuery(measures=[{"fn": "count"}, _PRICE], group_by=group_by),
        ALICE,
    )


def _shape(result: AggregateNodesResult) -> dict[str | None, tuple[str, int]]:
    """Each group as {item name or None: (label, size)}."""
    assert result.groups is not None
    return {
        None if g.key is None else NAMES[g.key]: (g.label, g.count)
        for g in result.groups
    }


def _gbp(value: float) -> MeasureValue:
    return MeasureValue(currencies=(CurrencyValue(currency="GBP", value=value),))


async def test_groups_by_the_item_a_relationship_points_to(
    world: Callable[[], Awaitable[AggregateNodes]],
) -> None:
    """An item with two makers is in both; a deleted or foreign maker is unset."""
    result = await _run(
        await world(),
        {"by": "related", "relationship": "made-by", "direction": "out"},
    )

    # f3's maker is deleted, f4's is Bob's, and the makers and the book have none.
    assert _shape(result) == {
        "Acme": ("Acme", 2),
        "Zeta": ("Zeta", 1),
        None: ("Unset", 5),
    }
    assert result.groups is not None
    by_name = {g.label: g.values for g in result.groups}
    # f2 has two makers, so it is in both totals; the deleted edge adds nothing.
    assert by_name["Acme"][1] == _gbp(15)
    assert by_name["Zeta"][1] == _gbp(5)
    assert by_name["Unset"][1] == _gbp(3)


async def test_groups_by_the_items_pointing_at_it(
    world: Callable[[], Awaitable[AggregateNodes]],
) -> None:
    """With `in`, a maker is grouped under each film that names it."""
    result = await _run(
        await world(),
        {"by": "related", "relationship": "made-by", "direction": "in"},
    )

    # Acme is named by f1 and f2, Zeta by f2 (its other edge is deleted).
    assert _shape(result) == {"f1": ("f1", 1), "f2": ("f2", 2), None: ("Unset", 5)}


async def test_a_relationship_with_no_direction_reads_either_end(
    world: Callable[[], Awaitable[AggregateNodes]],
) -> None:
    """Sequels are grouped under each other, whichever direction is asked."""
    use_case = await world()

    for direction in ("out", "in", "any"):
        result = await _run(
            use_case,
            {"by": "related", "relationship": "sequel", "direction": direction},
        )

        assert _shape(result) == {"f1": ("f1", 1), "f2": ("f2", 1), None: ("Unset", 5)}


async def test_the_limit_leaves_the_rest_in_other_once(
    world: Callable[[], Awaitable[AggregateNodes]],
) -> None:
    """An item with two hidden makers is in `other` once, and totalled once."""
    result = await _run(
        await world(),
        {
            "by": "related",
            "relationship": "made-by",
            "direction": "out",
            "order": "count",
            "limit": 1,
        },
    )

    assert result.groups is not None
    assert [g.label for g in result.groups] == ["Unset"]
    assert result.other is not None
    assert (result.other.groups, result.other.count) == (2, 2)
    assert result.other.values[1] == _gbp(15)


async def test_a_relationship_that_is_gone_warns(
    world: Callable[[], Awaitable[AggregateNodes]],
) -> None:
    """A removed relationship type gives no groups and a warning at `group_by`."""
    result = await _run(
        await world(), {"by": "related", "relationship": "nope", "direction": "out"}
    )

    assert result.groups == []
    assert [(w.path, w.message) for w in result.warnings] == [
        ("group_by", "That relationship no longer exists.")
    ]
