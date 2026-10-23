"""Expanding "in collection" conditions: smart inlining, limits and refusals."""

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
from app.modules.graph.adapters.persistence.in_memory_external_conditions import (
    InMemoryExternalConditions,
)
from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_node_type_repository import (
    InMemoryNodeTypeRepository,
)
from app.modules.graph.application.collection_expansion import (
    MAX_EXPANSIONS,
    MAX_NESTING,
)
from app.modules.graph.application.prepare_query import prepare_query
from app.modules.graph.application.validate_query import (
    ValidateQuery,
    ValidateQueryQuery,
)
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.domain.query import InvalidQueryError
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.content_filter import ContentFilter

ME = uuid.UUID(int=1)
TODAY = date(2026, 10, 18)
SCOPE = ContentFilter.of(ME)
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"rating": {"type": "number", "x-menagerist": {"kind": "rating"}}},
}


def _id(number: int) -> uuid.UUID:
    return uuid.UUID(int=0xE0000 + number)


def _in(*ids: uuid.UUID) -> dict[str, Any]:
    return {"kind": "collection", "mode": "any", "in": [str(i) for i in ids]}


def _query(*children: dict[str, Any]) -> dict[str, Any]:
    return {"v": 1, "where": {"op": "and", "children": list(children)}}


def _rating(op: str, value: int, key: str = "rating") -> dict[str, Any]:
    return {"kind": "field", "type": "film", "key": key, "op": op, "value": value}


async def _world() -> tuple[GraphRepos, InMemoryExternalConditions]:
    provider = InMemoryExternalConditions()
    repos = GraphRepos(
        nodes=InMemoryNodeRepository(provider),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
        external=provider,
        definitions=provider,
    )
    await repos.node_types.add(
        NodeType.create(slug="film", label="Film", attributes_schema=SCHEMA)
    )
    for rating in (1, 5):
        await repos.nodes.add(
            Node.create(
                owner_id=ME,
                name=f"R{rating}",
                type="film",
                attributes={"rating": rating},
            )
        )
    return repos, provider


async def _names(repos: GraphRepos, raw: dict[str, Any]) -> set[str]:
    resolved, _ = await prepare_query(repos, raw, TODAY, scope=SCOPE)
    hits = await repos.nodes.search(scope=SCOPE, resolved=resolved, after=None, limit=9)
    return {hit.node.name for hit in hits}


async def test_a_smart_collection_keeps_its_field_conditions() -> None:
    """The inlined filter is evaluated with the fields it names."""
    repos, provider = await _world()
    provider.add_collection(_id(1), owner_id=ME, definition=_query(_rating(">=", 3)))

    assert await _names(repos, _query(_in(_id(1)))) == {"R5"}


async def test_a_stale_field_inside_a_smart_collection_warns_with_a_nested_path() -> (
    None
):
    """The warning points into the collection, and the condition matches nothing."""
    repos, provider = await _world()
    provider.add_collection(
        _id(1), owner_id=ME, definition=_query(_rating(">=", 3, key="gone"))
    )
    raw = _query(_in(_id(1)))

    resolved, warnings = await prepare_query(repos, raw, TODAY, scope=SCOPE)

    assert [w.path for w in warnings] == ["where.children[0].in[0].children[0]"]
    assert await _names(repos, raw) == set()
    assert resolved.stale


async def test_an_unreadable_stored_definition_is_stale_not_an_error() -> None:
    """A smart collection whose search no longer parses degrades to nothing."""
    repos, provider = await _world()
    provider.add_collection(
        _id(1), owner_id=ME, definition={"v": 1, "where": {"op": "xor"}}
    )
    provider.add_collection(
        _id(2),
        owner_id=ME,
        definition=_query(_rating(">", 3)) | {"sort": [{"by": "nope"}]},
    )

    _, warnings = await prepare_query(
        repos, _query(_in(_id(1), _id(2))), TODAY, scope=SCOPE
    )

    assert [w.message for w in warnings] == [
        "That collection's search is no longer valid."
    ] * 2


async def test_a_wrongly_typed_value_in_a_stored_definition_is_stale() -> None:
    """A field that exists but no longer fits the value degrades, not a 400."""
    repos, provider = await _world()
    provider.add_collection(
        _id(1), owner_id=ME, definition=_query(_rating(">", 3) | {"value": "high"})
    )

    _, warnings = await prepare_query(repos, _query(_in(_id(1))), TODAY, scope=SCOPE)

    assert [w.message for w in warnings] == [
        "That collection's search is no longer valid."
    ]


async def test_expansions_are_capped_per_query() -> None:
    """Past the cap, further smart collections are stale rather than expanded."""
    repos, provider = await _world()
    provider.add_collection(_id(1), owner_id=ME, definition=_query(_rating(">", 3)))
    raw = _query(_in(*[_id(1)] * MAX_EXPANSIONS), _in(_id(1)), _in(_id(2)))
    provider.add_collection(_id(2), owner_id=ME, members=[])

    _, warnings = await prepare_query(repos, raw, TODAY, scope=SCOPE)

    assert [(w.path, w.message) for w in warnings] == [
        ("where.children[1].in[0]", "This search uses too many collections.")
    ]


async def test_nesting_limit_is_the_constant() -> None:
    """A chain one longer than the limit is stale at its last link."""
    repos, provider = await _world()
    last = MAX_NESTING + 1
    for number in range(1, last):
        provider.add_collection(
            _id(number), owner_id=ME, definition=_query(_in(_id(number + 1)))
        )
    provider.add_collection(_id(last), owner_id=ME, definition=_query(_rating(">", 3)))

    _, warnings = await prepare_query(repos, _query(_in(_id(1))), TODAY, scope=SCOPE)

    assert [w.message for w in warnings] == ["Collections are nested too deeply."]


async def test_validate_query_refuses_a_reference_back_to_the_collection_saved() -> (
    None
):
    """`self_id` makes a self reference a 400 naming its path."""
    repos, provider = await _world()
    provider.add_collection(_id(1), owner_id=ME, definition=_query(_in(_id(2))))
    provider.add_collection(_id(2), owner_id=ME, definition=_query(_in(_id(1))))
    use_case = ValidateQuery(repos, InMemoryAccessGuard())

    with pytest.raises(InvalidQueryError) as caught:
        await use_case.handle(
            ValidateQueryQuery(query=_query(_in(_id(2))), scope=SCOPE, self_id=_id(1)),
            SYSTEM_ACTOR,
        )

    assert caught.value.path == "where.children[0].in[0].children[0].in[0]"


async def test_validate_query_reports_collection_warnings() -> None:
    """A missing collection is a warning at the id's path."""
    repos, _ = await _world()

    result = await ValidateQuery(repos, InMemoryAccessGuard()).handle(
        ValidateQueryQuery(query=_query(_in(_id(9))), scope=SCOPE), SYSTEM_ACTOR
    )

    assert [w.path for w in result.warnings] == ["where.children[0].in[0]"]


async def test_the_everyone_scope_sees_every_owners_collections() -> None:
    """System paths with an unrestricted scope resolve any live collection."""
    repos, provider = await _world()
    provider.add_collection(_id(1), owner_id=uuid.UUID(int=77), members=[])

    _, warnings = await prepare_query(
        repos, _query(_in(_id(1))), TODAY, scope=ContentFilter.everyone()
    )

    assert warnings == []
