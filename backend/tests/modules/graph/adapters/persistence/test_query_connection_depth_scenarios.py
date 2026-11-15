"""Connections followed through several hops: one table, both adapters.

`direction: in` from an item walks to what contains it, so `to <box>` with `in`
means "inside that box"; `out` finds what holds the item.
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
from app.modules.graph.application.prepare_query import prepare_query
from app.modules.graph.domain.edge import Edge
from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.domain.node import Node
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.modules.graph.ports.unit_of_work import GraphRepos

ALICE = uuid.UUID(int=401)
BOB = uuid.UUID(int=402)
TODAY = date(2026, 11, 15)

# name -> (owner, tags, deleted)
ITEMS: dict[str, tuple[uuid.UUID, list[str], bool]] = {
    "shed": (ALICE, [], False),
    "box1": (ALICE, [], False),
    "box2": (ALICE, [], False),
    "bag": (ALICE, [], False),
    "coin": (ALICE, ["rare"], False),
    "lamp": (ALICE, [], False),
    "ring1": (ALICE, [], False),
    "ring2": (ALICE, [], False),
    "crate": (ALICE, [], False),
    "cut": (ALICE, [], True),
    "hidden": (ALICE, [], False),
    "top": (ALICE, [], False),
    "bobmid": (BOB, [], False),
    "under": (ALICE, [], False),
    "fan": (ALICE, [], False),
    "fan2": (ALICE, [], False),
}
ALICE_LIVE = {n for n, (o, _t, d) in ITEMS.items() if o == ALICE and not d}

# holder, held, relationship
EDGES: list[tuple[str, str, str]] = [
    ("shed", "box1", "contains"),
    ("shed", "box2", "contains"),
    ("box1", "bag", "contains"),
    ("bag", "coin", "contains"),
    ("box2", "lamp", "contains"),
    ("ring1", "ring2", "contains"),
    ("ring2", "ring1", "contains"),
    ("crate", "cut", "contains"),
    ("cut", "hidden", "contains"),
    ("top", "bobmid", "contains"),
    ("bobmid", "under", "contains"),
    ("fan", "fan2", "related"),
    ("shed", "coin", "related"),
]

IDS: dict[str, uuid.UUID] = {
    name: uuid.UUID(int=0x6000 + i) for i, name in enumerate(ITEMS)
}


def _where(*children: dict[str, Any], op: str = "and") -> dict[str, Any]:
    return {"v": 1, "where": {"op": op, "children": list(children)}}


def _held_by(name: str, depth: int, direction: str = "in") -> dict[str, Any]:
    return {
        "kind": "connection",
        "mode": "to",
        "item": str(IDS[name]),
        "relationship": "contains",
        "direction": direction,
        "depth": depth,
    }


def _holds(mode: str, depth: int, *tags: str) -> dict[str, Any]:
    tag = {"kind": "tag", "mode": "any", "tags": list(tags)}
    far = {"op": "and", "children": [tag]}
    return {
        "kind": "connection",
        "mode": mode,
        "relationship": "contains",
        "direction": "out",
        "depth": depth,
        "where": far,
    }


CASES: list[tuple[str, dict[str, Any], set[str], uuid.UUID]] = [
    ("inside the shed, one step", _where(_held_by("shed", 1)), {"box1", "box2"}, ALICE),
    (
        "inside the shed, two steps",
        _where(_held_by("shed", 2)),
        {"box1", "box2", "bag", "lamp"},
        ALICE,
    ),
    (
        "inside the shed, three steps",
        _where(_held_by("shed", 3)),
        {"box1", "box2", "bag", "lamp", "coin"},
        ALICE,
    ),
    (
        "inside the shed, the deepest allowed",
        _where(_held_by("shed", 25)),
        {"box1", "box2", "bag", "lamp", "coin"},
        ALICE,
    ),
    (
        "what holds the coin, any depth",
        _where(_held_by("coin", 25, direction="out")),
        {"bag", "box1", "shed"},
        ALICE,
    ),
    (
        "a loop is followed once and ends",
        _where(_held_by("ring1", 25)),
        {"ring2"},
        ALICE,
    ),
    (
        "a deleted item in between ends the chain",
        _where(_held_by("crate", 25)),
        set(),
        ALICE,
    ),
    (
        "another person's item in between ends the chain",
        _where(_held_by("top", 25)),
        set(),
        ALICE,
    ),
    (
        "holds something rare, one step",
        _where(_holds("exists", 1, "rare")),
        {"bag"},
        ALICE,
    ),
    (
        "holds something rare, two steps",
        _where(_holds("exists", 2, "rare")),
        {"bag", "box1"},
        ALICE,
    ),
    (
        "holds something rare, three steps",
        _where(_holds("exists", 3, "rare")),
        {"bag", "box1", "shed"},
        ALICE,
    ),
    (
        "holds nothing rare, three steps",
        _where(_holds("none", 3, "rare")),
        ALICE_LIVE - {"bag", "box1", "shed"},
        ALICE,
    ),
    (
        "not over holds something rare",
        _where({"op": "not", "children": [_holds("exists", 3, "rare")]}),
        ALICE_LIVE - {"bag", "box1", "shed"},
        ALICE,
    ),
    (
        "another person finds nothing inside Alice's shed",
        _where(_held_by("shed", 25)),
        set(),
        BOB,
    ),
]


async def _seed(repos: GraphRepos) -> None:
    for slug, label, directional in (
        ("contains", "Contains", True),
        ("related", "Related", False),
    ):
        await repos.edge_types.add(
            EdgeType.create(
                owner_id=ALICE, slug=slug, label=label, directional=directional
            )
        )
    for name, (owner, tags, deleted) in ITEMS.items():
        node = Node.create(owner_id=owner, name=name, type=None, tags=tags)
        node.id = IDS[name]
        if deleted:
            node.soft_delete()
        await repos.nodes.add(node)
    for holder, held, relationship in EDGES:
        await repos.edges.add(
            Edge.create(
                owner_id=ALICE,
                source_id=IDS[holder],
                target_id=IDS[held],
                type=relationship,
            )
        )


@pytest.fixture(
    params=["in_memory", pytest.param("postgres", marks=pytest.mark.integration)]
)
def seed(request: pytest.FixtureRequest) -> Callable[[], Awaitable[GraphRepos]]:
    """Seeds the same world on either adapter."""
    session = (
        None if request.param == "in_memory" else request.getfixturevalue("db_session")
    )

    async def build() -> GraphRepos:
        repos = (
            build_in_memory_graph_repos()
            if session is None
            else build_search_graph_repos(session)
        )
        await _seed(repos)
        return repos

    return build


async def _run(
    repos: GraphRepos, raw: dict[str, Any], user: uuid.UUID
) -> tuple[set[str], list[str]]:
    scope = ContentFilter.of(user)
    resolved, warnings = await prepare_query(repos, raw, TODAY, scope=scope)
    hits = await repos.nodes.search(
        scope=scope, resolved=resolved, after=None, limit=100
    )
    assert await repos.nodes.search_count(scope=scope, resolved=resolved) == len(hits)
    return {hit.node.name for hit in hits}, [w.path for w in warnings]


@pytest.mark.parametrize(
    ("label", "raw", "expected", "user"), CASES, ids=[c[0] for c in CASES]
)
async def test_scenario(
    seed: Callable[[], Awaitable[GraphRepos]],
    label: str,
    raw: dict[str, Any],
    expected: set[str],
    user: uuid.UUID,
) -> None:
    """Each scenario gives the same answer on both adapters."""
    names, _ = await _run(await seed(), raw, user)
    assert names == expected


async def test_a_non_directional_relationship_warns_and_matches_nothing(
    seed: Callable[[], Awaitable[GraphRepos]],
) -> None:
    """Several hops over a relationship with no direction is stale, not an error."""
    condition = {
        "kind": "connection",
        "mode": "exists",
        "relationship": "related",
        "direction": "out",
        "depth": 2,
    }
    names, warned = await _run(await seed(), _where(condition), ALICE)
    assert names == set()
    assert warned == ["where.children[0]"]


async def test_one_hop_over_a_non_directional_relationship_still_works(
    seed: Callable[[], Awaitable[GraphRepos]],
) -> None:
    """Depth one keeps today's either-end behaviour."""
    condition = {
        "kind": "connection",
        "mode": "exists",
        "relationship": "related",
        "direction": "out",
    }
    names, warned = await _run(await seed(), _where(condition), ALICE)
    assert names == {"fan", "fan2", "shed", "coin"}
    assert warned == []
