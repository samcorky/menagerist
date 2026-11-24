"""Conditions that name no list: every collection, every item type (#750).

A collection or type condition without `in` means all of them: "in a collection",
"in no collection", "has an item type", "has no item type". Both adapters give the
same answers; the in-memory evaluator is the reference.
"""

import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

import pytest

from app.entrypoints.api.shared.bridges.collection_conditions import (
    build_search_graph_repos,
)
from app.modules.collections.adapters.persistence.collection_repository import (
    SqlAlchemyCollectionRepository,
)
from app.modules.collections.adapters.persistence.membership_repository import (
    SqlAlchemyMembershipRepository,
)
from app.modules.collections.domain.collection import Collection, Membership
from app.modules.graph.adapters.persistence.in_memory_external_conditions import (
    InMemoryExternalConditions,
)
from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.application.prepare_query import prepare_query
from app.modules.graph.domain.node import Node
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.slug import Slug

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession

ALICE = uuid.UUID(int=301)
BOB = uuid.UUID(int=302)
CAROL = uuid.UUID(int=303)
TODAY = date(2026, 11, 24)
NOW = datetime(2026, 11, 24, tzinfo=UTC)

MANUAL = uuid.UUID(int=0xE1000001)
SMART = uuid.UUID(int=0xE1000002)
BOBS = uuid.UUID(int=0xE1000003)

# name -> (owner, item type, favourite). Alice has a book in a manual collection, a
# favourite film (the smart collection), a loose item with no type, and a loose book.
ITEMS: dict[str, tuple[uuid.UUID, str | None, bool]] = {
    "a": (ALICE, "book", False),
    "b": (ALICE, "film", True),
    "c": (ALICE, None, False),
    "d": (ALICE, "book", False),
    "bobs": (BOB, None, False),
    "carols": (CAROL, "book", False),
}
MEMBERS = {MANUAL: {"a"}, BOBS: {"bobs"}}
SMART_DEFINITION = {
    "v": 1,
    "where": {
        "op": "and",
        "children": [{"kind": "favourite", "value": True}],
    },
}


def _where(condition: dict[str, Any]) -> dict[str, Any]:
    return {"v": 1, "where": {"op": "and", "children": [condition]}}


def _collection(mode: str) -> dict[str, Any]:
    return _where({"kind": "collection", "mode": mode})


def _type(mode: str, *slugs: str) -> dict[str, Any]:
    condition: dict[str, Any] = {"kind": "type", "mode": mode}
    if slugs:
        condition["in"] = list(slugs)
    return _where(condition)


CASES: list[tuple[str, dict[str, Any], set[str], uuid.UUID]] = [
    ("in a collection, manual or smart", _collection("any"), {"a", "b"}, ALICE),
    ("in no collection", _collection("none"), {"c", "d"}, ALICE),
    ("each owner sees only their own collections", _collection("any"), {"bobs"}, BOB),
    ("no collections at all: nothing is in one", _collection("any"), set(), CAROL),
    (
        "no collections at all: everything is in none",
        _collection("none"),
        {"carols"},
        CAROL,
    ),
    ("has an item type", _type("any"), {"a", "b", "d"}, ALICE),
    ("has no item type", _type("none"), {"c"}, ALICE),
    ("a type listed", _type("any", "book"), {"a", "d"}, ALICE),
    ("not a listed type, untyped included", _type("none", "book"), {"b", "c"}, ALICE),
    ("not any of two types", _type("none", "book", "film"), {"c"}, ALICE),
    (
        "no type and in no collection together",
        {
            "v": 1,
            "where": {
                "op": "and",
                "children": [
                    {"kind": "type", "mode": "none"},
                    {"kind": "collection", "mode": "none"},
                ],
            },
        },
        {"c"},
        ALICE,
    ),
    (
        "the old form still means any of the types",
        _where({"kind": "type", "in": ["film"]}),
        {"b"},
        ALICE,
    ),
]


async def _seed_memory() -> GraphRepos:
    provider = InMemoryExternalConditions()
    nodes = InMemoryNodeRepository(provider)
    ids: dict[str, uuid.UUID] = {}
    for name, (owner, type_, favourite) in ITEMS.items():
        node = Node.create(owner_id=owner, name=name, type=type_)
        node.favourite = favourite
        ids[name] = node.id
        await nodes.add(node)
    provider.add_collection(MANUAL, owner_id=ALICE, members=[ids["a"]])
    provider.add_collection(SMART, owner_id=ALICE, definition=SMART_DEFINITION)
    provider.add_collection(BOBS, owner_id=BOB, members=[ids["bobs"]])
    return GraphRepos(
        nodes=nodes,
        edges=None,  # type: ignore[arg-type]
        node_types=_NoTypes(),  # type: ignore[arg-type]
        edge_types=None,  # type: ignore[arg-type]
        external=provider,
        definitions=provider,
    )


class _NoTypes:
    async def list(self, *, scope: Any, after: Any, limit: int) -> list[Any]:  # noqa: ANN401
        return []


async def _seed_postgres(session: AsyncSession) -> GraphRepos:
    repos = build_search_graph_repos(session)
    ids: dict[str, uuid.UUID] = {}
    for name, (owner, type_, favourite) in ITEMS.items():
        node = Node.create(owner_id=owner, name=name, type=type_)
        node.favourite = favourite
        ids[name] = node.id
        await repos.nodes.add(node)
    collections = SqlAlchemyCollectionRepository(session)
    memberships = SqlAlchemyMembershipRepository(session)
    for cid, owner, definition in (
        (MANUAL, ALICE, None),
        (SMART, ALICE, SMART_DEFINITION),
        (BOBS, BOB, None),
    ):
        collection = Collection.create(
            name=f"c{cid.int & 0xFF}",
            slug=Slug(f"c{cid.int & 0xFF}"),
            owner_id=owner,
            definition=definition,
        )
        collection.id = cid
        await collections.add(collection)
    for cid, members in MEMBERS.items():
        for member in members:
            await memberships.add(
                Membership(collection_id=cid, item_id=ids[member], added_at=NOW)
            )
    return repos


@pytest.fixture(
    params=["in_memory", pytest.param("postgres", marks=pytest.mark.integration)]
)
def seed(request: pytest.FixtureRequest) -> Callable[[], Awaitable[GraphRepos]]:
    """Seeds the same world on either adapter; awaiting it gives the repositories."""
    if request.param == "in_memory":
        return _seed_memory
    session = request.getfixturevalue("db_session")
    return lambda: _seed_postgres(session)


async def _names(repos: GraphRepos, raw: dict[str, Any], user: uuid.UUID) -> set[str]:
    scope = ContentFilter.of(user)
    resolved, _ = await prepare_query(repos, raw, TODAY, scope=scope)
    hits = await repos.nodes.search(
        scope=scope, resolved=resolved, after=None, limit=100
    )
    counted = await repos.nodes.search_count(scope=scope, resolved=resolved)
    assert counted == len(hits)
    return {hit.node.name for hit in hits}


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
    repos = await seed()
    assert await _names(repos, raw, user) == expected


async def test_a_smart_collection_can_hold_what_is_in_no_other_collection() -> None:
    """Saving "in no collection" as a smart collection leaves itself out of "every"."""
    repos = await _seed_memory()
    scope = ContentFilter.of(ALICE)
    raw = _collection("none")
    resolved, warnings = await prepare_query(
        repos, raw, TODAY, scope=scope, self_id=SMART
    )
    hits = await repos.nodes.search(
        scope=scope, resolved=resolved, after=None, limit=100
    )

    assert warnings == []
    # With itself left out, only the manual collection counts: b is no longer in one.
    assert {hit.node.name for hit in hits} == {"b", "c", "d"}
