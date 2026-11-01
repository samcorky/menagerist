"""Connection conditions: one table of scenarios, both adapters.

The in-memory evaluator is the reference; the Postgres run compiles the same
conditions to correlated EXISTS over `edges`.
"""

import uuid
from datetime import date
from typing import TYPE_CHECKING, Any

import pytest

from app.entrypoints.api.shared.bridges.collection_conditions import (
    build_search_graph_repos,
)
from app.modules.collections.adapters.persistence.collection_repository import (
    SqlAlchemyCollectionRepository,
)
from app.modules.collections.domain.collection import Collection
from app.modules.graph.adapters.persistence.in_memory_external_conditions import (
    InMemoryExternalConditions,
)
from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.adapters.persistence.query_eval import sort_values
from app.modules.graph.adapters.persistence.unit_of_work import (
    build_in_memory_graph_repos,
)
from app.modules.graph.application.prepare_query import prepare_query
from app.modules.graph.domain.edge import Edge
from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.domain.query import Cursor
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.slug import Slug

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.graph.ports.unit_of_work import GraphRepos

ALICE = uuid.UUID(int=301)
BOB = uuid.UUID(int=302)
TODAY = date(2026, 10, 24)

_YEAR_SCHEMA = {"type": "object", "properties": {"year": {"type": "number"}}}

# name -> (owner, type, year, tags, deleted)
ITEMS: dict[str, tuple[uuid.UUID, str, int | None, list[str], bool]] = {
    "f1": (ALICE, "film", 2001, [], False),
    "f2": (ALICE, "film", 1990, [], False),
    "f3": (ALICE, "film", None, [], False),
    "lonely": (ALICE, "film", None, [], False),
    "f5": (ALICE, "film", None, [], False),
    "f6": (ALICE, "film", None, [], False),
    "f7": (ALICE, "film", None, [], False),
    "d1": (ALICE, "person", None, ["star"], False),
    "d2": (ALICE, "person", None, [], False),
    "gone": (ALICE, "person", None, [], True),
    "bobp": (BOB, "person", None, [], False),
}
ALICE_LIVE = {n for n, (o, *_rest, d) in ITEMS.items() if o == ALICE and not d}

# source, target, relationship, owner, deleted
EDGES: list[tuple[str, str, str, uuid.UUID, bool]] = [
    ("f1", "d1", "directed-by", ALICE, False),
    ("f2", "d2", "directed-by", ALICE, False),
    ("f3", "gone", "directed-by", ALICE, False),
    ("f5", "d1", "directed-by", ALICE, True),
    ("f1", "f2", "related", ALICE, False),
    ("f6", "bobp", "directed-by", ALICE, False),
    ("f7", "d1", "retired", ALICE, False),
]


def _where(*children: dict[str, Any], op: str = "and") -> dict[str, Any]:
    return {"v": 1, "where": {"op": op, "children": list(children)}}


def _conn(mode: str = "exists", **extra: Any) -> dict[str, Any]:  # noqa: ANN401
    return {"kind": "connection", "mode": mode, **extra}


def _not(child: dict[str, Any]) -> dict[str, Any]:
    return {"op": "not", "children": [child]}


def _far(*children: dict[str, Any]) -> dict[str, Any]:
    return {"op": "and", "children": list(children)}


_PERSON = {"kind": "type", "in": ["person"]}
_STAR = {"kind": "tag", "mode": "any", "tags": ["star"]}
_RECENT = {"kind": "field", "type": "film", "key": "year", "op": ">", "value": 2000}
_REMOVED = {"kind": "field", "type": "film", "key": "removed", "op": "=", "value": 1}

IDS: dict[str, uuid.UUID] = {
    name: uuid.UUID(int=0x5000 + i) for i, name in enumerate(ITEMS)
}


def _to(name: str, **extra: Any) -> dict[str, Any]:  # noqa: ANN401
    return _conn("to", item=str(IDS[name]), **extra)


def _everyone_but(*names: str) -> set[str]:
    return ALICE_LIVE - set(names)


LINKED = {"f1", "f2", "d1", "d2", "f7"}

CASES: list[tuple[str, dict[str, Any], set[str], uuid.UUID]] = [
    ("exists", _where(_conn()), LINKED, ALICE),
    (
        "none, including items with no connections",
        _where(_conn("none")),
        ALICE_LIVE - LINKED,
        ALICE,
    ),
    (
        "exists skips deleted edges, deleted far items and other owners' items",
        _where(_conn()),
        LINKED - {"f3", "f5", "f6"},
        ALICE,
    ),
    (
        "a relationship, either end",
        _where(_conn(relationship="directed-by")),
        {"f1", "f2", "d1", "d2"},
        ALICE,
    ),
    (
        "a relationship, out",
        _where(_conn(relationship="directed-by", direction="out")),
        {"f1", "f2"},
        ALICE,
    ),
    (
        "a relationship, in",
        _where(_conn(relationship="directed-by", direction="in")),
        {"d1", "d2"},
        ALICE,
    ),
    (
        "any relationship, out is the stored source",
        _where(_conn(direction="out")),
        {"f1", "f2", "f7"},
        ALICE,
    ),
    (
        "any relationship, in is the stored target",
        _where(_conn(direction="in")),
        {"d1", "d2", "f2"},
        ALICE,
    ),
    (
        "a non-directional type ignores out",
        _where(_conn(relationship="related", direction="out")),
        {"f1", "f2"},
        ALICE,
    ),
    (
        "a non-directional type ignores in",
        _where(_conn(relationship="related", direction="in")),
        {"f1", "f2"},
        ALICE,
    ),
    (
        "none of a relationship",
        _where(_conn("none", relationship="directed-by")),
        _everyone_but("f1", "f2", "d1", "d2"),
        ALICE,
    ),
    (
        "none, out",
        _where(_conn("none", relationship="directed-by", direction="out")),
        _everyone_but("f1", "f2"),
        ALICE,
    ),
    (
        "none of a non-directional type",
        _where(_conn("none", relationship="related")),
        _everyone_but("f1", "f2"),
        ALICE,
    ),
    ("not exists equals none", _where(_not(_conn())), ALICE_LIVE - LINKED, ALICE),
    ("to an item", _where(_to("d1")), {"f1", "f7"}, ALICE),
    (
        "to an item by relationship",
        _where(_to("d1", relationship="directed-by")),
        {"f1"},
        ALICE,
    ),
    ("to an item, out", _where(_to("d1", direction="out")), {"f1", "f7"}, ALICE),
    ("to an item the wrong way round", _where(_to("d1", direction="in")), set(), ALICE),
    ("to an item, in", _where(_to("f1", direction="in")), {"d1", "f2"}, ALICE),
    (
        "to an item, in, by relationship",
        _where(_to("f1", relationship="directed-by", direction="in")),
        {"d1"},
        ALICE,
    ),
    (
        "to an item by a non-directional type",
        _where(_to("f1", relationship="related")),
        {"f2"},
        ALICE,
    ),
    ("to a deleted item is stale", _where(_to("gone")), set(), ALICE),
    (
        "not to a deleted item is stale too",
        _where(_not(_to("gone"))),
        ALICE_LIVE,
        ALICE,
    ),
    ("to another owner's item is stale", _where(_to("bobp")), set(), ALICE),
    (
        "exists with a far type",
        _where(_conn(where=_far(_PERSON))),
        {"f1", "f2", "f7"},
        ALICE,
    ),
    (
        "exists with a far field",
        _where(_conn(where=_far(_RECENT))),
        {"f2", "d1"},
        ALICE,
    ),
    ("exists with a far tag", _where(_conn(where=_far(_STAR))), {"f1", "f7"}, ALICE),
    (
        "exists with a far filter and a relationship",
        _where(_conn(relationship="related", where=_far(_RECENT))),
        {"f2"},
        ALICE,
    ),
    (
        "exists with a far filter and a direction",
        _where(_conn(direction="in", where=_far(_RECENT))),
        {"d1", "f2"},
        ALICE,
    ),
    (
        "exists with a far filter over several conditions",
        _where(_conn(where=_far(_PERSON, _STAR))),
        {"f1", "f7"},
        ALICE,
    ),
    (
        "none with a far filter",
        _where(_conn("none", where=_far(_PERSON))),
        ALICE_LIVE - {"f1", "f2", "f7"},
        ALICE,
    ),
    (
        "not over exists with a far filter",
        _where(_not(_conn(where=_far(_STAR)))),
        ALICE_LIVE - {"f1", "f7"},
        ALICE,
    ),
    (
        "not over a far filter's own not",
        _where(_conn(where=_far(_not(_PERSON)))),
        {"f1", "f2", "d1", "d2"},
        ALICE,
    ),
    (
        "a far filter naming a removed field is stale",
        _where(_conn(where=_far(_REMOVED))),
        set(),
        ALICE,
    ),
    (
        "not over that stale far filter",
        _where(_not(_conn(where=_far(_REMOVED)))),
        ALICE_LIVE,
        ALICE,
    ),
    (
        "none with that stale far filter finds no far item to exclude",
        _where(_conn("none", where=_far(_REMOVED))),
        ALICE_LIVE,
        ALICE,
    ),
    (
        "a deleted relationship type matches nothing",
        _where(_conn(relationship="retired")),
        set(),
        ALICE,
    ),
    (
        "none of a deleted relationship type matches nothing",
        _where(_conn("none", relationship="retired")),
        set(),
        ALICE,
    ),
    (
        "not over a deleted relationship type",
        _where(_not(_conn(relationship="retired"))),
        ALICE_LIVE,
        ALICE,
    ),
    (
        "an unknown relationship matches nothing",
        _where(_conn(relationship="nope")),
        set(),
        ALICE,
    ),
    (
        "or with another condition",
        _where(_conn("none"), {"kind": "name", "op": "=", "value": "d1"}, op="or"),
        (ALICE_LIVE - LINKED) | {"d1"},
        ALICE,
    ),
    (
        "and with another condition",
        _where(_conn(), {"kind": "type", "in": ["person"]}),
        {"d1", "d2"},
        ALICE,
    ),
    ("another owner's item sees none of Alice's edges", _where(_conn()), set(), BOB),
    (
        "another owner's none still counts their lone item",
        _where(_conn("none")),
        {"bobp"},
        BOB,
    ),
]


async def _seed(repos: GraphRepos) -> None:
    await repos.node_types.add(
        NodeType.create(slug="film", label="Film", attributes_schema=_YEAR_SCHEMA)
    )
    await repos.node_types.add(NodeType.create(slug="person", label="Person"))
    await repos.edge_types.add(EdgeType.create(slug="directed-by", label="Directed by"))
    await repos.edge_types.add(
        EdgeType.create(slug="related", label="Related", directional=False)
    )
    retired = EdgeType.create(slug="retired", label="Retired")
    retired.soft_delete()
    await repos.edge_types.add(retired)
    for name, (owner, type_slug, year, tags, deleted) in ITEMS.items():
        node = Node.create(
            owner_id=owner,
            name=name,
            type=type_slug,
            attributes={} if year is None else {"year": year},
            tags=tags,
        )
        node.id = IDS[name]
        if deleted:
            node.soft_delete()
        await repos.nodes.add(node)
    for source, target, relationship, owner, deleted in EDGES:
        edge = Edge.create(
            owner_id=owner,
            source_id=IDS[source],
            target_id=IDS[target],
            type=relationship,
        )
        if deleted:
            edge.soft_delete()
        await repos.edges.add(edge)


@pytest.fixture(
    params=["in_memory", pytest.param("postgres", marks=pytest.mark.integration)]
)
def seed(request: pytest.FixtureRequest) -> Callable[..., Awaitable[GraphRepos]]:
    """Seeds the same world on either adapter; awaiting it gives the repositories."""
    session = (
        None if request.param == "in_memory" else request.getfixturevalue("db_session")
    )

    async def build(smart: dict[uuid.UUID, dict[str, Any]] | None = None) -> GraphRepos:
        repos = (
            _in_memory_repos() if session is None else build_search_graph_repos(session)
        )
        await _seed(repos)
        for collection_id, definition in (smart or {}).items():
            await _add_smart_collection(repos, session, collection_id, definition)
        return repos

    return build


def _in_memory_repos() -> GraphRepos:
    provider = InMemoryExternalConditions()
    return build_in_memory_graph_repos(external=provider, definitions=provider)


async def _add_smart_collection(
    repos: GraphRepos,
    session: AsyncSession | None,
    collection_id: uuid.UUID,
    definition: dict[str, Any],
) -> None:
    if session is None:
        assert isinstance(repos.definitions, InMemoryExternalConditions)
        repos.definitions.add_collection(
            collection_id, owner_id=ALICE, definition=definition
        )
        return
    collection = Collection.create(
        name=str(collection_id),
        slug=Slug(f"c{collection_id.int}"),
        owner_id=ALICE,
        definition=definition,
    )
    collection.id = collection_id
    await SqlAlchemyCollectionRepository(session).add(collection)


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
    seed: Callable[..., Awaitable[GraphRepos]],
    label: str,
    raw: dict[str, Any],
    expected: set[str],
    user: uuid.UUID,
) -> None:
    """Each scenario gives the same answer on both adapters."""
    repos = await seed()
    names, _ = await _run(repos, raw, user)
    assert names == expected


@pytest.mark.parametrize(
    ("label", "raw", "paths"),
    [
        ("live", _where(_conn(relationship="directed-by")), []),
        ("deleted type", _where(_conn(relationship="retired")), ["where.children[0]"]),
        (
            "unknown type",
            _where(_conn("none", relationship="nope")),
            ["where.children[0]"],
        ),
        ("deleted item", _where(_to("gone")), ["where.children[0]"]),
        ("other owner's item", _where(_to("bobp")), ["where.children[0]"]),
        (
            "stale far field",
            _where(_conn(where=_far(_RECENT, _REMOVED))),
            ["where.children[0].where.children[1]"],
        ),
    ],
    ids=lambda v: v if isinstance(v, str) else "",
)
async def test_warnings_carry_the_condition_path(
    seed: Callable[..., Awaitable[GraphRepos]],
    label: str,
    raw: dict[str, Any],
    paths: list[str],
) -> None:
    """A stale part warns with the path of the condition (or the nested field)."""
    repos = await seed()
    _, warned = await _run(repos, raw, ALICE)
    assert warned == paths


async def test_sorting_paging_and_the_total_follow_the_filter(
    seed: Callable[..., Awaitable[GraphRepos]],
) -> None:
    """Pages of a connection filter keep their order and the count stays whole."""
    repos = await seed()
    scope = ContentFilter.of(ALICE)
    raw = {**_where(_conn()), "sort": [{"by": "name", "dir": "desc"}]}
    resolved, _ = await prepare_query(repos, raw, TODAY, scope=scope)
    first = await repos.nodes.search(
        scope=scope, resolved=resolved, after=None, limit=2
    )
    cursor = Cursor(
        sort_values=sort_values(first[-1].node, resolved), id=first[-1].node.id
    )
    rest = await repos.nodes.search(
        scope=scope, resolved=resolved, after=cursor, limit=10
    )
    names = [h.node.name for h in [*first, *rest]]
    assert names == sorted(LINKED, reverse=True)
    assert len(first) == 2
    assert await repos.nodes.search_count(scope=scope, resolved=resolved) == len(LINKED)
    assert await repos.nodes.search_count(scope=scope, resolved=resolved, limit=2) == 2


async def test_an_in_memory_repository_without_edges_matches_no_connections() -> None:
    """Built bare, as before, connection conditions find nothing."""
    nodes = InMemoryNodeRepository()
    await nodes.add(Node.create(owner_id=ALICE, name="x", type="film"))
    repos = build_in_memory_graph_repos()
    repos.nodes = nodes
    scope = ContentFilter.of(ALICE)
    for mode in ("exists", "none"):
        resolved, _ = await prepare_query(
            repos, _where(_conn(mode)), TODAY, scope=scope
        )
        hits = await nodes.search(scope=scope, resolved=resolved, after=None, limit=9)
        assert [h.node.name for h in hits] == ([] if mode == "exists" else ["x"])


_HAS_A_CONNECTION = uuid.UUID(int=0xC1)
_NEXT_TO_A_STAR = uuid.UUID(int=0xC2)
_NEXT_TO_THAT = uuid.UUID(int=0xC3)
_FILM = {"kind": "type", "in": ["film"]}


def _in_collection(collection_id: uuid.UUID) -> dict[str, Any]:
    return {"kind": "collection", "mode": "any", "in": [str(collection_id)]}


@pytest.mark.parametrize(
    ("label", "smart", "target", "expected"),
    [
        (
            "a smart collection that is itself a connection",
            {_HAS_A_CONNECTION: _where(_conn())},
            _HAS_A_CONNECTION,
            {"f1", "f2", "f7"},
        ),
        (
            "a smart collection whose connection has its own far filter",
            {_NEXT_TO_A_STAR: _where(_conn(where=_far(_STAR)))},
            _NEXT_TO_A_STAR,
            {"f2"},
        ),
        (
            "a smart collection whose far filter names another such collection",
            {
                _NEXT_TO_A_STAR: _where(_conn(where=_far(_STAR))),
                _NEXT_TO_THAT: _where(
                    _conn(where=_far(_in_collection(_NEXT_TO_A_STAR)))
                ),
            },
            _NEXT_TO_THAT,
            {"f1", "f7"},
        ),
    ],
    ids=lambda v: v if isinstance(v, str) else "",
)
async def test_a_far_filter_may_name_a_smart_collection_with_connections(
    seed: Callable[..., Awaitable[GraphRepos]],
    label: str,
    smart: dict[uuid.UUID, dict[str, Any]],
    target: uuid.UUID,
    expected: set[str],
) -> None:
    """A second connection level is reachable through a collection."""
    repos = await seed(smart)
    raw = _where(_FILM, _conn(where=_far(_in_collection(target))))
    names, warned = await _run(repos, raw, ALICE)
    assert names == expected
    assert warned == []
