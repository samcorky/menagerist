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
from app.modules.graph.application.query_cursor import encode_cursor
from app.modules.graph.application.search_nodes import (
    TOTAL_CAP,
    SearchNodes,
    SearchNodesQuery,
)
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.domain.query import Cursor, InvalidQueryError, SortValue
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "rating": {"type": "number", "x-menagerist": {"kind": "rating"}},
        "title": {"type": "string", "x-menagerist": {"kind": "text"}},
        "price": {"type": "object", "x-menagerist": {"kind": "money"}},
        "released": {"type": "string", "format": "date"},
        "old_rating": {"type": "number", "x-menagerist": {"archived": True}},
    },
}


async def _setup(count: int = 5, **options: Any) -> SearchNodes:  # noqa: ANN401
    repos = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )
    await repos.node_types.add(
        NodeType.create(slug="film", label="Film", attributes_schema=SCHEMA)
    )
    for index in range(count):
        await repos.nodes.add(
            Node.create(
                owner_id=uuid.UUID(int=1),
                name=f"Film {index}",
                type="film",
                attributes={"rating": index % 3, "old_rating": 2},
            )
        )
    return SearchNodes(
        repos, InMemoryAccessGuard(), today=lambda: date(2026, 10, 14), **options
    )


def _body(*children: dict[str, Any], **extra: Any) -> dict[str, Any]:  # noqa: ANN401
    where = {"op": "and", "children": list(children)} if children else None
    return {"v": 1, "where": where, **extra}


def _rating(op: str, value: int) -> dict[str, Any]:
    return {"kind": "field", "type": "film", "key": "rating", "op": op, "value": value}


async def test_returns_matches_and_total() -> None:
    """SearchNodes: returns matches and total."""
    use_case = await _setup()
    result = await use_case.handle(
        SearchNodesQuery(query=_body(_rating(">=", 1))), SYSTEM_ACTOR
    )
    assert [n.name for n in result.items] == ["Film 1", "Film 2", "Film 4"]
    assert result.total == 3
    assert result.next_cursor is None
    assert result.warnings == []


async def test_pages_with_a_cursor() -> None:
    """SearchNodes: pages with a cursor."""
    use_case = await _setup()
    body = _body(sort=[{"by": "name"}])
    first = await use_case.handle(SearchNodesQuery(query=body, limit=2), SYSTEM_ACTOR)
    assert [n.name for n in first.items] == ["Film 0", "Film 1"]
    assert first.total == 5
    assert first.next_cursor is not None
    second = await use_case.handle(
        SearchNodesQuery(query=body, limit=2, cursor=first.next_cursor), SYSTEM_ACTOR
    )
    assert [n.name for n in second.items] == ["Film 2", "Film 3"]
    last = await use_case.handle(
        SearchNodesQuery(query=body, limit=2, cursor=second.next_cursor), SYSTEM_ACTOR
    )
    assert [n.name for n in last.items] == ["Film 4"]
    assert last.next_cursor is None


async def test_stale_fields_are_reported() -> None:
    """SearchNodes: stale fields are reported."""
    use_case = await _setup()
    stale = {"kind": "field", "type": "film", "key": "gone", "op": "=", "value": "x"}
    result = await use_case.handle(SearchNodesQuery(query=_body(stale)), SYSTEM_ACTOR)
    assert result.items == []
    assert [w.path for w in result.warnings] == ["where.children[0]"]


async def test_stale_reference_matches_nothing_beside_a_live_condition() -> None:
    """SearchNodes: a stale reference is not revived by a live condition."""
    use_case = await _setup()
    stale = _rating("<=", 0) | {"value": {"ref": "old_rating"}}
    live = {"kind": "field", "type": "film", "key": "rating", "op": "not_empty"}
    result = await use_case.handle(
        SearchNodesQuery(query=_body(stale, live)), SYSTEM_ACTOR
    )
    assert result.items == []
    assert [w.path for w in result.warnings] == ["where.children[0]"]


async def test_invalid_queries_are_rejected() -> None:
    """SearchNodes: invalid queries are rejected."""
    use_case = await _setup()
    with pytest.raises(InvalidQueryError):
        await use_case.handle(SearchNodesQuery(query={"v": 9}), SYSTEM_ACTOR)
    with pytest.raises(InvalidQueryError, match="limit"):
        await use_case.handle(SearchNodesQuery(query=_body(), limit=0), SYSTEM_ACTOR)
    with pytest.raises(InvalidQueryError, match="cursor"):
        await use_case.handle(
            SearchNodesQuery(query=_body(), cursor="nope"), SYSTEM_ACTOR
        )


async def test_other_users_items_are_invisible() -> None:
    """SearchNodes: other users items are invisible."""
    use_case = await _setup(count=0)
    alice = Actor(id=uuid.UUID(int=11), roles=frozenset({"member"}))
    bob = Actor(id=uuid.UUID(int=12), roles=frozenset({"member"}))
    for actor, name in ((alice, "Alice's film"), (bob, "Bob's film")):
        await use_case._repos.nodes.add(
            Node.create(owner_id=actor.id, name=name, type="film")
        )
    for actor, expected in ((alice, "Alice's film"), (bob, "Bob's film")):
        result = await use_case.handle(SearchNodesQuery(query=_body()), actor)
        assert [n.name for n in result.items] == [expected]


def _sorted(*sort: dict[str, Any]) -> dict[str, Any]:
    return _body(sort=list(sort))


def _token(*values: SortValue, node_id: uuid.UUID | None = None) -> str:
    cursor = Cursor(sort_values=values, id=node_id or uuid.UUID(int=5))
    return encode_cursor(cursor)


_FIELD_RATING = {"by": "field", "type": "film", "key": "rating"}
_FIELD_PRICE = {"by": "field", "type": "film", "key": "price"}
_FIELD_TITLE = {"by": "field", "type": "film", "key": "title"}
_FIELD_DATE = {"by": "field", "type": "film", "key": "released"}
_STALE = {"by": "field", "type": "film", "key": "gone"}


@pytest.mark.parametrize(
    ("sort", "value"),
    [
        ({"by": "name"}, 1),
        ({"by": "created"}, "x"),
        ({"by": "updated"}, "x"),
        (_FIELD_RATING, "x"),
        (_FIELD_PRICE, "x"),
        (_FIELD_TITLE, 3),
        (_FIELD_DATE, 3),
        (_STALE, "x"),
        (_STALE, 3),
    ],
)
async def test_cursor_value_of_the_wrong_type_is_rejected(
    sort: dict[str, Any], value: SortValue
) -> None:
    """SearchNodes: cursor value of the wrong type is rejected."""
    use_case = await _setup()
    query = SearchNodesQuery(query=_sorted(sort), cursor=_token(value))
    with pytest.raises(InvalidQueryError) as caught:
        await use_case.handle(query, SYSTEM_ACTOR)
    assert caught.value.path == "cursor"


@pytest.mark.parametrize(
    ("sort", "value"),
    [
        ({"by": "name"}, "Film 1"),
        ({"by": "created"}, 1.5),
        ({"by": "updated"}, 2),
        (_FIELD_RATING, 1),
        (_FIELD_PRICE, 9.5),
        (_FIELD_TITLE, "a"),
        (_FIELD_DATE, "2026-01-01"),
        (_STALE, None),
        ({"by": "name"}, None),
        (_FIELD_RATING, None),
    ],
)
async def test_cursor_value_of_the_right_type_is_accepted(
    sort: dict[str, Any], value: SortValue
) -> None:
    """SearchNodes: cursor value of the right type is accepted."""
    use_case = await _setup()
    query = SearchNodesQuery(query=_sorted(sort), cursor=_token(value))
    result = await use_case.handle(query, SYSTEM_ACTOR)
    assert result.total == 5


@pytest.mark.parametrize("limit", [0, -1, 201])
async def test_limit_out_of_bounds_is_rejected(limit: int) -> None:
    """SearchNodes: limit out of bounds is rejected."""
    use_case = await _setup()
    with pytest.raises(InvalidQueryError) as caught:
        await use_case.handle(
            SearchNodesQuery(query=_body(), limit=limit), SYSTEM_ACTOR
        )
    assert caught.value.path == "limit"


async def test_limit_bounds_are_accepted() -> None:
    """SearchNodes: limit bounds are accepted."""
    use_case = await _setup()
    for limit in (1, 200):
        result = await use_case.handle(
            SearchNodesQuery(query=_body(), limit=limit), SYSTEM_ACTOR
        )
        assert result.total == 5


async def test_stale_sort_field_warns_and_still_pages() -> None:
    """SearchNodes: stale sort field warns and still pages."""
    use_case = await _setup()
    result = await use_case.handle(
        SearchNodesQuery(query=_sorted(_STALE)), SYSTEM_ACTOR
    )
    assert result.warnings
    assert result.total == 5


async def test_default_clock_is_utc_today() -> None:
    """SearchNodes: default clock is utc today."""
    use_case = await _setup()
    default = SearchNodes(use_case._repos, InMemoryAccessGuard())
    result = await default.handle(SearchNodesQuery(query=_body()), SYSTEM_ACTOR)
    assert result.total == 5


async def test_or_group_never_returns_other_users_items() -> None:
    """SearchNodes: or group never returns other users items."""
    use_case = await _setup(count=0)
    alice = Actor(id=uuid.UUID(int=11), roles=frozenset({"member"}))
    bob = Actor(id=uuid.UUID(int=12), roles=frozenset({"member"}))
    for owner, name in ((alice, "A"), (bob, "B")):
        await use_case._repos.nodes.add(
            Node.create(
                owner_id=owner.id, name=name, type="film", attributes={"rating": 1}
            )
        )
    body = {
        "v": 1,
        "where": {
            "op": "or",
            "children": [
                {"kind": "favourite", "value": False},
                _rating("=", 1),
            ],
        },
    }
    result = await use_case.handle(SearchNodesQuery(query=body), alice)
    assert [n.name for n in result.items] == ["A"]
    assert result.total == 1


def test_default_total_cap_is_one_thousand() -> None:
    """SearchNodes: the cap constant is 1,000."""
    assert TOTAL_CAP == 1000


async def test_default_cap_applies_when_none_is_given() -> None:
    """SearchNodes: a default-constructed use case caps at TOTAL_CAP."""
    use_case = await _setup(TOTAL_CAP + 1)
    result = await use_case.handle(SearchNodesQuery(query=_body()), SYSTEM_ACTOR)
    assert result.total == TOTAL_CAP
    assert result.total_capped is True


@pytest.mark.parametrize(
    ("count", "total", "capped"), [(5, 3, True), (3, 3, False), (2, 2, False)]
)
async def test_total_is_capped(count: int, total: int, capped: bool) -> None:
    """SearchNodes: total stops at the cap and says so; the page is unaffected."""
    use_case = await _setup(count, total_cap=3)
    result = await use_case.handle(
        SearchNodesQuery(query=_body(), limit=4), SYSTEM_ACTOR
    )
    assert result.total == total
    assert result.total_capped is capped
    assert len(result.items) == min(count, 4)
