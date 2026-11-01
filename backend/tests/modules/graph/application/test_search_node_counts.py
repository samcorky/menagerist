import uuid
from datetime import date
from typing import Any

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
from app.modules.graph.application.search_node_counts import (
    MAX_QUERIES,
    SearchCount,
    SearchNodeCounts,
    SearchNodeCountsQuery,
)
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.domain.query import InvalidQueryError
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import Actor

ALICE = Actor(id=uuid.UUID(int=11), roles=frozenset({"member"}))
BOB = Actor(id=uuid.UUID(int=12), roles=frozenset({"member"}))
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "rating": {"type": "number", "x-menagerist": {"kind": "rating"}},
        "old_rating": {"type": "number", "x-menagerist": {"archived": True}},
    },
}
EVERYTHING: dict[str, Any] = {"v": 1, "where": None, "sort": []}
FILMS: dict[str, Any] = {
    "v": 1,
    "where": {"op": "and", "children": [{"kind": "type", "in": ["film"]}]},
    "sort": [],
}


def _empty_repos() -> GraphRepos:
    return GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )


async def _use_case(
    *,
    films: int = 3,
    books: int = 1,
    **options: Any,  # noqa: ANN401
) -> SearchNodeCounts:
    repos = _empty_repos()
    await repos.node_types.add(
        NodeType.create(slug="film", label="Film", attributes_schema=SCHEMA)
    )
    for _ in range(films):
        await repos.nodes.add(Node.create(owner_id=ALICE.id, name="f", type="film"))
    for _ in range(books):
        await repos.nodes.add(Node.create(owner_id=ALICE.id, name="b"))
    await repos.nodes.add(Node.create(owner_id=BOB.id, name="theirs", type="film"))
    return SearchNodeCounts(
        repos, InMemoryAccessGuard(), today=lambda: date(2026, 10, 14), **options
    )


async def test_counts_each_named_query() -> None:
    """Counts each named query."""
    use_case = await _use_case()

    result = await use_case.handle(
        SearchNodeCountsQuery(queries={"all": EVERYTHING, "films": FILMS}), ALICE
    )

    assert result == {
        "all": SearchCount(total=4, capped=False, warnings=[]),
        "films": SearchCount(total=3, capped=False, warnings=[]),
    }


async def test_counts_only_the_actors_own_items() -> None:
    """Counts only the actors own items."""
    use_case = await _use_case()

    result = await use_case.handle(
        SearchNodeCountsQuery(queries={"all": EVERYTHING}), BOB
    )

    assert result["all"].total == 1


async def test_ignores_the_sort_but_still_checks_it() -> None:
    """A sorted query counts the same; a bad sort is still rejected."""
    use_case = await _use_case()
    sorted_query = {**FILMS, "sort": [{"by": "created", "dir": "desc"}]}

    result = await use_case.handle(
        SearchNodeCountsQuery(queries={"s": sorted_query}), ALICE
    )
    assert result["s"].total == 3
    with pytest.raises(InvalidQueryError):
        await use_case.handle(
            SearchNodeCountsQuery(queries={"s": {**FILMS, "sort": [{"by": "nope"}]}}),
            ALICE,
        )


async def test_counts_exactly_up_to_the_cap_and_flags_more() -> None:
    """Counts exactly up to the cap and says when it stopped counting."""
    at_cap = await (await _use_case(films=3, books=0, count_cap=3)).handle(
        SearchNodeCountsQuery(queries={"f": FILMS}), ALICE
    )
    over = await (await _use_case(films=4, books=0, count_cap=3)).handle(
        SearchNodeCountsQuery(queries={"f": FILMS}), ALICE
    )

    assert at_cap["f"] == SearchCount(total=3, capped=False, warnings=[])
    assert over["f"] == SearchCount(total=3, capped=True, warnings=[])


async def test_reports_stale_conditions_as_warnings_per_query() -> None:
    """Reports stale conditions as warnings, per query."""
    use_case = await _use_case()
    stale = {
        "v": 1,
        "where": {
            "op": "and",
            "children": [
                {
                    "kind": "field",
                    "type": "film",
                    "key": "old_rating",
                    "op": ">",
                    "value": 1,
                }
            ],
        },
        "sort": [],
    }

    result = await use_case.handle(
        SearchNodeCountsQuery(queries={"stale": stale, "films": FILMS}), ALICE
    )

    assert len(result["stale"].warnings) == 1
    assert result["films"].warnings == []


async def test_a_bad_query_names_which_one_failed() -> None:
    """A malformed query is a 400 that names the query by its key."""
    use_case = await _use_case()

    with pytest.raises(InvalidQueryError) as caught:
        await use_case.handle(
            SearchNodeCountsQuery(
                queries={"ok": EVERYTHING, "bad": {"v": 1, "where": {"op": "xor"}}}
            ),
            ALICE,
        )

    assert caught.value.path == "queries.bad"
    assert str(caught.value).startswith("queries.bad: ")


@pytest.mark.parametrize(
    "queries",
    [
        {},
        {str(i): EVERYTHING for i in range(MAX_QUERIES + 1)},
        {"": EVERYTHING},
        {"x" * 65: EVERYTHING},
        {"has space": EVERYTHING},
    ],
    ids=["none", "too many", "empty name", "long name", "odd name"],
)
async def test_rejects_a_batch_that_is_empty_too_large_or_badly_named(
    queries: dict[str, Any],
) -> None:
    """Rejects a batch that is empty, too large or badly named."""
    use_case = await _use_case()

    with pytest.raises(InvalidQueryError) as caught:
        await use_case.handle(SearchNodeCountsQuery(queries=queries), ALICE)

    assert caught.value.path == "queries"


async def test_the_default_clock_is_utc_today() -> None:
    """A relative date resolves with the default clock."""
    repos = _empty_repos()
    relative = {
        "v": 1,
        "where": {
            "op": "and",
            "children": [
                {"kind": "date", "on": "created", "op": ">=", "value": {"rel": "-30d"}}
            ],
        },
        "sort": [],
    }
    await repos.nodes.add(Node.create(owner_id=ALICE.id, name="new"))

    result = await SearchNodeCounts(repos, InMemoryAccessGuard()).handle(
        SearchNodeCountsQuery(queries={"month": relative}), ALICE
    )

    assert result["month"].total == 1
