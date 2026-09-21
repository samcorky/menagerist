from typing import Any

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
from app.modules.graph.application.schema_meta import search_excluded_keys
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.actor import SYSTEM_ACTOR

_FILM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "director": {"type": "string"},
        "year": {"type": "number"},
        "seen": {"type": "boolean"},
        "stars": {"type": "number", "x-menagerist": {"kind": "rating"}},
        "old_note": {"type": "string", "x-menagerist": {"archived": True}},
        "internal": {"type": "string", "x-menagerist": {"search": False}},
        "cast": {"type": "array", "items": {"type": "object"}},
    },
}


def _repos() -> GraphRepos:
    return GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )


async def _search(repos: GraphRepos, q: str) -> list[Node]:
    result = await ListNodes(repos).handle(ListNodesQuery(q=q), SYSTEM_ACTOR)
    return result.items


async def _film_repos() -> tuple[GraphRepos, Node]:
    repos = _repos()
    await repos.node_types.add(
        NodeType.create(slug="film", label="Film", attributes_schema=_FILM_SCHEMA)
    )
    film = Node.create(
        name="Alien",
        type="film",
        attributes={
            "director": "Ridley Scott",
            "year": 1979,
            "seen": True,
            "stars": 5,
            "old_note": "gooey",
            "internal": "secret",
            "cast": [{"name": "Sigourney Weaver", "role": "Ripley"}],
            "extra": "Nostromo",
        },
    )
    await repos.nodes.add(film)
    return repos, film


async def test_search_finds_string_number_group_cell_and_undefined_key() -> None:
    """Text and numbers match anywhere, including group cells and custom details."""
    repos, film = await _film_repos()

    for q in ("scott", "1979", "ripley", "WEAVER", "nostromo"):
        assert await _search(repos, q) == [film], q


async def test_search_ignores_keys_booleans_and_ratings() -> None:
    """Key names, booleans and ratings are never matched."""
    repos, _ = await _film_repos()

    for q in ("director", "true", "role", "sigourney_weaver_x"):
        assert await _search(repos, q) == [], q


async def test_search_skips_archived_and_opted_out_fields() -> None:
    """Archived and `search: false` values no longer match, and only for that type."""
    repos, _ = await _film_repos()
    other = Node.create(name="Other", type="person", attributes={"old_note": "gooey"})
    untyped = Node.create(name="Loose", attributes={"internal": "secret"})
    await repos.nodes.add(other)
    await repos.nodes.add(untyped)

    assert await _search(repos, "gooey") == [other]
    assert await _search(repos, "secret") == [untyped]


async def test_search_scans_untyped_nodes_in_full() -> None:
    """A node without a type is searched in every attribute."""
    repos = _repos()
    node = Node.create(name="Loose", attributes={"stars": 5, "note": "hello"})
    await repos.nodes.add(node)

    assert await _search(repos, "hello") == [node]
    assert await _search(repos, "5") == [node]


async def test_search_still_matches_name_and_description() -> None:
    """Name and description matching is unchanged."""
    repos = _repos()
    a = Node.create(name="Alien", description="a xenomorph")
    await repos.nodes.add(a)

    assert await _search(repos, "alien") == [a]
    assert await _search(repos, "xeno") == [a]


async def test_search_treats_percent_and_underscore_literally() -> None:
    """Wildcard characters in the query match only themselves."""
    repos = _repos()
    pct = Node.create(name="100% sure")
    plain = Node.create(name="Plain")
    await repos.nodes.add(pct)
    await repos.nodes.add(plain)

    assert await _search(repos, "%") == [pct]
    assert await _search(repos, "_") == []


async def test_search_total_agrees_with_items() -> None:
    """The total counts the same nodes the list returns."""
    repos, film = await _film_repos()
    await repos.nodes.add(Node.create(name="Unrelated"))

    result = await ListNodes(repos).handle(ListNodesQuery(q="scott"), SYSTEM_ACTOR)

    assert result.items == [film]
    assert result.total == 1


async def test_search_loads_every_page_of_node_types() -> None:
    """Exclusions come from all node types, not just the first page."""
    repos = _repos()
    for i in range(101):
        schema = {"properties": {"hidden": {"x-menagerist": {"archived": True}}}}
        await repos.node_types.add(
            NodeType.create(
                slug=f"type-{i:03d}", label=f"Type {i}", attributes_schema=schema
            )
        )
    nodes = [
        Node.create(name=f"n{i}", type=f"type-{i:03d}", attributes={"hidden": "zzz"})
        for i in (0, 100)
    ]
    for node in nodes:
        await repos.nodes.add(node)

    assert await _search(repos, "zzz") == []


async def test_list_without_search_does_not_load_node_types() -> None:
    """A plain listing needs no node types."""
    repos = _repos()
    node = Node.create(name="Alien")
    await repos.nodes.add(node)

    result = await ListNodes(repos).handle(ListNodesQuery(), SYSTEM_ACTOR)

    assert result.items == [node]


def test_search_excluded_keys_lists_archived_opt_out_and_rating() -> None:
    """Only archived, `search: false` and rating fields are excluded."""
    assert sorted(search_excluded_keys(_FILM_SCHEMA)) == [
        "internal",
        "old_note",
        "stars",
    ]


def test_search_excluded_keys_handles_missing_properties() -> None:
    """A schema without usable properties excludes nothing."""
    assert search_excluded_keys({}) == []
    assert search_excluded_keys({"properties": "nope"}) == []
