"""Smart collections through the real app and real bridges, for two people.

Each test runs over in-memory repositories and, integration-marked, on Postgres.
"""

import asyncio
import json
import uuid
from typing import TYPE_CHECKING, Any

import pytest
import sqlalchemy
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.bridges.collection_conditions import (
    CollectionsDefinitions,
)
from app.entrypoints.api.shared.bridges.collection_definitions import (
    GraphDefinitionChecker,
    get_definition_checker,
)
from app.entrypoints.api.shared.bridges.collection_items import (
    GraphItemLookup,
    get_item_lookup,
)
from app.entrypoints.api.shared.bridges.collection_members import (
    CollectionsMembers,
    get_collection_members,
)
from app.entrypoints.api.shared.bridges.example_targets import (
    build_in_memory_collections_repos,
)
from app.entrypoints.api.shared.dependencies import get_current_actor
from app.modules.collections.adapters.api.dependencies import (
    get_collections_repos,
    get_collections_uow,
)
from app.modules.collections.adapters.persistence.unit_of_work import (
    create_in_memory_collections_uow,
)
from app.modules.graph.adapters.api.dependencies import get_graph_repos, get_graph_uow
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
from app.modules.graph.adapters.persistence.unit_of_work import (
    create_in_memory_graph_uow,
)
from app.modules.graph.domain.node import Node
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.platform.database import get_engine, get_session_factory
from app.shared_kernel.actor import Actor
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from fastapi import FastAPI

ALICE = Actor(id=uuid.UUID(int=0xA1), roles=frozenset({"member"}))
BOB = Actor(id=uuid.UUID(int=0xB2), roles=frozenset({"member"}))
NODES = "/api/v1/node"
COLLECTIONS = "/api/v1/collection"
RATED: dict[str, Any] = {
    "type": "object",
    "properties": {
        "rating": {"type": "number", "x-menagerist": {"kind": "rating"}},
    },
}


class Env:
    """The app as a client, acting as whoever `actor` is."""

    def __init__(
        self,
        app: FastAPI,
        client: TestClient,
        bulk: Callable[[uuid.UUID, str, int], None],
        store_definition: Callable[[str, object], None],
    ) -> None:
        self.bulk = bulk
        self.store_definition = store_definition
        self.actor = ALICE
        app.dependency_overrides[get_current_actor] = lambda: self.actor
        self.client = client

    def as_(self, actor: Actor) -> TestClient:
        """Act as `actor` from now on and return the client."""
        self.actor = actor
        return self.client

    def item(self, name: str, **body: Any) -> str:  # noqa: ANN401
        """Create an item as the current actor and return its id."""
        response = self.client.post(NODES, json={"name": name, **body})
        assert response.status_code == 201, response.text
        item_id: str = response.json()["id"]
        return item_id

    def smart(self, definition: dict[str, Any], name: str = "Smart") -> dict[str, Any]:
        """Create a smart collection as the current actor and return its body."""
        response = self.client.post(
            COLLECTIONS, json={"name": name, "definition": definition}
        )
        assert response.status_code == 201, response.text
        body: dict[str, Any] = response.json()
        return body


def _in_memory_app() -> tuple[
    FastAPI,
    Callable[[uuid.UUID, str, int], None],
    Callable[[str, object], None],
]:
    app = create_app()
    collections = build_in_memory_collections_repos()
    graph = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
        definitions=CollectionsDefinitions(collections),
    )
    o = app.dependency_overrides
    o[get_graph_uow] = lambda: create_in_memory_graph_uow(graph)
    o[get_graph_repos] = lambda: graph
    o[get_collections_uow] = lambda: create_in_memory_collections_uow(collections)
    o[get_collections_repos] = lambda: collections
    o[get_item_lookup] = lambda: GraphItemLookup(graph)
    o[get_collection_members] = lambda: CollectionsMembers(collections)
    o[get_definition_checker] = lambda: GraphDefinitionChecker(graph)

    def bulk(owner_id: uuid.UUID, type_slug: str, count: int) -> None:
        async def add_all() -> None:
            for n in range(count):
                node = Node.create(
                    owner_id=owner_id, name=f"{type_slug} {n}", type=type_slug
                )
                await graph.nodes.add(node)

        asyncio.run(add_all())

    def store_definition(collection_id: str, definition: object) -> None:
        """Write a definition straight into the store, as a legacy row would hold."""

        async def put() -> None:
            found = await collections.collections.get(
                uuid.UUID(collection_id), scope=ContentFilter.everyone()
            )
            assert found is not None
            found.definition = definition  # type: ignore[assignment]

        asyncio.run(put())

    return app, bulk, store_definition


def _postgres_bulk(
    sync_url: str,
) -> Callable[[uuid.UUID, str, int], None]:
    def bulk(owner_id: uuid.UUID, type_slug: str, count: int) -> None:
        engine = sqlalchemy.create_engine(sync_url)
        with engine.begin() as connection:
            connection.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO nodes (id, owner_id, name, type, attributes,
                                       favourite, tags, created_at, updated_at)
                    SELECT gen_random_uuid(), :owner, :slug || ' ' || n, :slug,
                           '{}'::jsonb, false, '[]'::jsonb, now(), now()
                    FROM generate_series(1, :count) AS n
                    """
                ),
                {"owner": owner_id, "slug": type_slug, "count": count},
            )
        engine.dispose()

    return bulk


def _postgres_store_definition(sync_url: str) -> Callable[[str, object], None]:
    def store(collection_id: str, definition: object) -> None:
        engine = sqlalchemy.create_engine(sync_url)
        with engine.begin() as connection:
            connection.execute(
                sqlalchemy.text(
                    "UPDATE collections SET definition = CAST(:d AS jsonb) "
                    + "WHERE id = :id"
                ),
                {"d": json.dumps(definition), "id": collection_id},
            )
        engine.dispose()

    return store


def _wipe(sync_url: str) -> None:
    engine = sqlalchemy.create_engine(sync_url)
    with engine.begin() as connection:
        for table in ("collection_members", "collections", "edges", "nodes"):
            connection.execute(sqlalchemy.text(f"DELETE FROM {table}"))
        connection.execute(sqlalchemy.text("DELETE FROM node_types"))
    engine.dispose()


@pytest.fixture(
    params=["memory", pytest.param("postgres", marks=pytest.mark.integration)]
)
def env(request: pytest.FixtureRequest) -> Iterator[Env]:
    """The real app over in-memory repositories or Postgres, as Alice."""
    if request.param == "memory":
        app, bulk, store = _in_memory_app()
        yield Env(app, TestClient(app), bulk, store)
        return
    request.getfixturevalue("postgres_url")
    sync_url: str = request.getfixturevalue("postgres_sync_url")
    get_session_factory.cache_clear()
    get_engine.cache_clear()
    try:
        app = create_app()
        with TestClient(app) as client:
            yield Env(
                app,
                client,
                _postgres_bulk(sync_url),
                _postgres_store_definition(sync_url),
            )
    finally:
        get_session_factory.cache_clear()
        get_engine.cache_clear()
        _wipe(sync_url)


def _rating(op: str, value: object) -> dict[str, Any]:
    return {"kind": "field", "type": "film", "key": "rating", "op": op, "value": value}


def _where(*children: dict[str, Any], op: str = "and") -> dict[str, Any]:
    return {
        "v": 1,
        "where": {"op": op, "children": list(children)},
        "sort": [{"by": "name", "dir": "desc"}],
    }


def _films(env: Env) -> dict[str, str]:
    """Alice's films and a book, and Bob's film that matches every query."""
    a = env.as_(ALICE)
    film = a.post(
        "/api/v1/node-type",
        json={"slug": "film", "label": "Film", "attributes_schema": RATED},
    )
    assert film.status_code == 201, film.text
    assert a.post("/api/v1/node-type", json={"slug": "book", "label": "Book"})
    ids = {
        "Alien": env.item("Alien", type="film", attributes={"rating": 5}),
        "Aliens": env.item(
            "Aliens", type="film", attributes={"rating": 4}, favourite=True
        ),
        "Heat": env.item("Heat", type="film", attributes={"rating": 4}),
        "Ronin": env.item("Ronin", type="film", attributes={"rating": 2}),
        "Alien Book": env.item("Alien Book", type="book"),
        "film-type-id": film.json()["id"],
    }
    env.as_(BOB)
    ids["Bob's Alien"] = env.item("Bob's Alien", type="film", attributes={"rating": 5})
    env.as_(ALICE)
    return ids


def _names(response: Any) -> set[str]:  # noqa: ANN401
    assert response.status_code == 200, response.text
    return {n["name"] for n in response.json()}


def test_lists_exactly_the_matching_items_anded_with_filters(env: Env) -> None:
    """GET /node?collection=<smart> is the saved query AND q, type and favourite."""
    _films(env)
    smart = env.smart(_where(_rating(">=", 4)))
    a = env.as_(ALICE)
    url = f"{NODES}?collection={smart['id']}"

    listed = a.get(url)

    assert _names(listed) == {"Alien", "Aliens", "Heat"}
    assert listed.headers["Total-Count"] == "3"
    assert smart["item_count"] == 3
    assert _names(a.get(f"{url}&q=alien")) == {"Alien", "Aliens"}
    assert _names(a.get(f"{url}&type=book")) == set()
    assert _names(a.get(f"{url}&favourite=true")) == {"Aliens"}
    combined = a.get(f"{url}&q=alien&type=film&favourite=false")
    assert _names(combined) == {"Alien"}
    assert combined.headers["Total-Count"] == "1"


def test_pages_with_link_across_a_boundary(env: Env) -> None:
    """The Link header walks the matches in id order, with no gaps or repeats."""
    ids = _films(env)
    smart = env.smart(_where(_rating(">=", 4)))
    a = env.as_(ALICE)

    first = a.get(f"{NODES}?collection={smart['id']}&limit=2")
    assert first.headers["Total-Count"] == "3"
    next_url = first.links["next"]["url"]
    second = a.get(next_url)

    seen = [n["id"] for n in first.json()] + [n["id"] for n in second.json()]
    assert seen == sorted([ids["Alien"], ids["Aliens"], ids["Heat"]])
    assert "Link" not in second.headers


def test_another_persons_smart_collection_never_leaks(env: Env) -> None:
    """Bob gets 404 for Alice's smart collection everywhere, as for an unknown id."""
    _films(env)
    smart = env.smart(_where(_rating(">=", 4)), name="Alice's best")
    b = env.as_(BOB)
    unknown = uuid.uuid7()

    for path in (f"{COLLECTIONS}/{{}}", f"{NODES}?collection={{}}"):
        mine = b.get(path.format(smart["id"]))
        ghost = b.get(path.format(unknown))
        assert mine.status_code == ghost.status_code == 404
        assert mine.json()["title"] == ghost.json()["title"]
        assert "Alien" not in mine.text
    assert (
        b.patch(
            f"{COLLECTIONS}/{smart['id']}", json={"definition": {"v": 1}}
        ).status_code
        == 404
    )
    assert (
        b.put(f"{COLLECTIONS}/{smart['id']}/item", json={"item_ids": []}).status_code
        == 404
    )
    assert b.delete(f"{COLLECTIONS}/{smart['id']}/item/{unknown}").status_code == 404
    assert b.get(COLLECTIONS).json() == []


def test_a_smart_collection_never_counts_or_lists_others_items(env: Env) -> None:
    """Bob's matching film never reaches Alice's list or count, and vice versa."""
    _films(env)
    alice_smart = env.smart(_where(_rating("=", 5)))
    env.as_(BOB)
    bob_smart = env.smart(_where(_rating("=", 5)))

    b = env.as_(BOB)
    assert _names(b.get(f"{NODES}?collection={bob_smart['id']}")) == {"Bob's Alien"}
    assert b.get(f"{COLLECTIONS}/{bob_smart['id']}").json()["item_count"] == 1
    a = env.as_(ALICE)
    assert _names(a.get(f"{NODES}?collection={alice_smart['id']}")) == {"Alien"}
    [listed] = a.get(COLLECTIONS).json()
    assert listed["item_count"] == 1


def test_adding_and_removing_items_is_409(env: Env) -> None:
    """Membership of a smart collection cannot be edited by hand."""
    ids = _films(env)
    smart = env.smart(_where(_rating(">=", 4)))
    a = env.as_(ALICE)

    added = a.put(
        f"{COLLECTIONS}/{smart['id']}/item", json={"item_ids": [ids["Ronin"]]}
    )
    removed = a.delete(f"{COLLECTIONS}/{smart['id']}/item/{ids['Alien']}")

    assert added.status_code == removed.status_code == 409
    assert added.json()["title"] == "CollectionKindError"
    assert _names(a.get(f"{NODES}?collection={smart['id']}")) == {
        "Alien",
        "Aliens",
        "Heat",
    }


def test_invalid_definition_is_400_with_a_path(env: Env) -> None:
    """A definition the query engine rejects is a 400 naming where it went wrong."""
    _films(env)
    bad = _where({"kind": "field", "type": "film", "key": "rating", "op": "~"})

    response = env.as_(ALICE).post(COLLECTIONS, json={"name": "Bad", "definition": bad})

    assert response.status_code == 400
    assert response.json()["detail"].startswith("where.children[0]: ")


def test_a_stale_field_warns_and_lists_nothing(env: Env) -> None:
    """A removed field is a warning on GET and matches nothing in the list."""
    ids = _films(env)
    smart = env.smart(_where(_rating(">=", 4)))
    a = env.as_(ALICE)
    url = f"{COLLECTIONS}/{smart['id']}"
    before = a.get(url)

    archived = {
        "type": "object",
        "properties": {
            "rating": {
                "type": "number",
                "x-menagerist": {"kind": "rating", "archived": True},
            }
        },
    }
    patched = a.patch(
        f"/api/v1/node-type/{ids['film-type-id']}",
        json={"attributes_schema": archived},
    )
    assert patched.status_code == 200, patched.text
    after = a.get(url)

    assert before.json()["warnings"] == []
    assert [w["path"] for w in after.json()["warnings"]] == ["where.children[0]"]
    assert after.json()["item_count"] == 0
    assert after.headers["ETag"] != before.headers["ETag"]
    listed = a.get(f"{NODES}?collection={smart['id']}")
    assert listed.json() == []
    assert listed.headers["Total-Count"] == "0"


def test_a_stale_field_in_an_or_moves_the_etag_at_the_same_count(env: Env) -> None:
    """Archiving a used field changes the ETag even when count and time hold."""
    ids = _films(env)
    smart = env.smart(
        _where({"kind": "text", "q": "alien"}, _rating(">=", 100), op="or")
    )
    a = env.as_(ALICE)
    url = f"{COLLECTIONS}/{smart['id']}"
    before = a.get(url)
    archived = {
        "type": "object",
        "properties": {
            "rating": {
                "type": "number",
                "x-menagerist": {"kind": "rating", "archived": True},
            }
        },
    }
    a.patch(
        f"/api/v1/node-type/{ids['film-type-id']}",
        json={"attributes_schema": archived},
    )

    after = a.get(url, headers={"If-None-Match": before.headers["ETag"]})

    assert after.status_code == 200
    assert after.json()["item_count"] == before.json()["item_count"] == 3
    assert after.json()["updated_at"] == before.json()["updated_at"]
    assert after.json()["warnings"] != []
    assert after.headers["ETag"] != before.headers["ETag"]


def test_etag_changes_when_an_item_starts_matching(env: Env) -> None:
    """An item edited into the query moves the count and the ETag."""
    ids = _films(env)
    smart = env.smart(_where(_rating(">=", 4)))
    a = env.as_(ALICE)
    url = f"{COLLECTIONS}/{smart['id']}"
    old = a.get(url).headers["ETag"]

    edited = a.patch(f"{NODES}/{ids['Ronin']}", json={"attributes": {"rating": 5}})
    assert edited.status_code == 200, edited.text
    fresh = a.get(url, headers={"If-None-Match": old})

    assert fresh.status_code == 200
    assert fresh.json()["item_count"] == 4
    assert fresh.headers["ETag"] != old
    assert a.get(url, headers={"If-None-Match": fresh.headers["ETag"]}).status_code == (
        304
    )


def test_patching_the_definition_returns_the_new_count(env: Env) -> None:
    """PATCH stores the new definition and answers with its count and ETag."""
    _films(env)
    smart = env.smart(_where(_rating(">=", 4)))
    a = env.as_(ALICE)
    url = f"{COLLECTIONS}/{smart['id']}"
    narrower = _where(_rating("=", 5))

    patched = a.patch(url, json={"definition": narrower})

    assert patched.status_code == 200, patched.text
    assert patched.json()["definition"] == narrower
    assert patched.json()["item_count"] == 1
    current = a.get(url)
    assert current.json() == patched.json()
    assert current.headers["ETag"] == patched.headers["ETag"]
    assert _names(a.get(f"{NODES}?collection={smart['id']}")) == {"Alien"}


def test_manual_collections_are_unchanged(env: Env) -> None:
    """A manual collection beside a smart one still lists exactly its items."""
    ids = _films(env)
    env.smart(_where(_rating(">=", 4)))
    a = env.as_(ALICE)
    shelf = a.post(COLLECTIONS, json={"name": "Shelf"}).json()
    put = a.put(f"{COLLECTIONS}/{shelf['id']}/item", json={"item_ids": [ids["Ronin"]]})
    assert put.status_code == 200

    assert _names(a.get(f"{NODES}?collection={shelf['id']}")) == {"Ronin"}
    assert a.get(f"{COLLECTIONS}/{shelf['id']}").json()["kind"] == "manual"


def _rating_as_text(env: Env, film_type_id: str) -> None:
    """Change `rating` to a text field, so `>=` no longer fits it."""
    schema = {
        "type": "object",
        "properties": {"rating": {"type": "string", "x-menagerist": {"kind": "text"}}},
    }
    patched = env.as_(ALICE).patch(
        f"/api/v1/node-type/{film_type_id}", json={"attributes_schema": schema}
    )
    assert patched.status_code == 200, patched.text


def test_count_is_exact_above_the_cap(env: Env) -> None:
    """The count route passes the 1,000 cap that the collection's own count hits."""
    _films(env)
    a = env.as_(ALICE)
    assert a.post("/api/v1/node-type", json={"slug": "coin", "label": "Coin"})
    env.bulk(ALICE.id, "coin", 1005)
    smart = env.smart(
        {"v": 1, "where": {"op": "and", "children": [{"kind": "text", "q": "coin"}]}}
    )

    capped = a.get(f"{COLLECTIONS}/{smart['id']}").json()
    exact = a.get(f"{COLLECTIONS}/{smart['id']}/count")

    assert (capped["item_count"], capped["item_count_capped"]) == (1000, True)
    assert exact.status_code == 200
    assert exact.json() == {"count": 1005}


def test_count_of_a_manual_collection_is_its_live_members(env: Env) -> None:
    """Members count; items deleted since are not."""
    ids = _films(env)
    a = env.as_(ALICE)
    shelf = a.post(COLLECTIONS, json={"name": "Shelf"}).json()
    members = [ids["Alien"], ids["Heat"], ids["Ronin"]]
    a.put(f"{COLLECTIONS}/{shelf['id']}/item", json={"item_ids": members})
    assert a.delete(f"{NODES}/{ids['Ronin']}").status_code == 204

    assert a.get(f"{COLLECTIONS}/{shelf['id']}/count").json() == {"count": 2}


def test_count_applies_the_definition_only_to_the_callers_items(env: Env) -> None:
    """Bob's matching film is not in Alice's count."""
    _films(env)
    smart = env.smart(_where(_rating("=", 5)))

    assert env.as_(ALICE).get(f"{COLLECTIONS}/{smart['id']}/count").json() == {
        "count": 1
    }


def test_count_of_a_stale_definition_is_zero(env: Env) -> None:
    """A removed field matches nothing, without an error."""
    ids = _films(env)
    smart = env.smart(_where(_rating(">=", 4)))
    archived = {
        "type": "object",
        "properties": {
            "rating": {
                "type": "number",
                "x-menagerist": {"kind": "rating", "archived": True},
            }
        },
    }
    a = env.as_(ALICE)
    a.patch(
        f"/api/v1/node-type/{ids['film-type-id']}",
        json={"attributes_schema": archived},
    )

    counted = a.get(f"{COLLECTIONS}/{smart['id']}/count")

    assert counted.status_code == 200
    assert counted.json() == {"count": 0}


def test_count_of_a_definition_that_no_longer_validates_is_zero(env: Env) -> None:
    """A field whose kind changed under the query counts 0, never a 500."""
    ids = _films(env)
    smart = env.smart(_where(_rating(">=", 4)))
    _rating_as_text(env, ids["film-type-id"])

    counted = env.as_(ALICE).get(f"{COLLECTIONS}/{smart['id']}/count")

    assert counted.status_code == 200
    assert counted.json() == {"count": 0}


def test_another_persons_count_is_404_like_an_unknown_id(env: Env) -> None:
    """Bob learns nothing about Alice's smart or manual collection."""
    _films(env)
    smart = env.smart(_where(_rating(">=", 4)))
    shelf = env.as_(ALICE).post(COLLECTIONS, json={"name": "Shelf"}).json()
    b = env.as_(BOB)
    ghost = b.get(f"{COLLECTIONS}/{uuid.uuid7()}/count")

    for collection in (smart, shelf):
        theirs = b.get(f"{COLLECTIONS}/{collection['id']}/count")
        assert theirs.status_code == ghost.status_code == 404
        assert theirs.json()["title"] == ghost.json()["title"]
        assert "count" not in theirs.json()


def _deep(levels: int) -> dict[str, Any]:
    node: Any = 1
    for _ in range(levels):
        node = {"d": node}
    return {"v": 1, "deep": node}


_HOSTILE: dict[str, bytes] = {
    "nul in an extra key": json.dumps({"v": 1, "note": "a\u0000b"}).encode(),
    "nul in a condition": json.dumps(
        {
            "v": 1,
            "where": {
                "op": "and",
                "children": [{"kind": "favourite", "value": True, "x": "\u0000"}],
            },
        }
    ).encode(),
    "lone surrogate": b'{"v": 1, "note": "\\ud800"}',
    "800 levels deep": json.dumps(_deep(800)).encode(),
    "1 MB of junk": json.dumps({"v": 1, "junk": "x" * 1_000_000}).encode(),
    "an unknown key": json.dumps({"v": 1, "note": "hello"}).encode(),
    "NaN": b'{"v": 1, "n": NaN}',
}


@pytest.mark.parametrize("name", list(_HOSTILE))
def test_hostile_definitions_are_400_and_the_list_stays_healthy(
    env: Env, name: str
) -> None:
    """Every probe from the review is refused on create and on update."""
    a = env.as_(ALICE)
    json_type = {"Content-Type": "application/json"}
    body = b'{"name": "Hostile", "definition": ' + _HOSTILE[name] + b"}"
    created = a.post(COLLECTIONS, content=body, headers=json_type)
    assert created.status_code == 400, created.text

    smart = env.smart(_where(_rating(">=", 1)), name="Fine")
    patched = a.patch(
        f"{COLLECTIONS}/{smart['id']}",
        content=b'{"definition": ' + _HOSTILE[name] + b"}",
        headers=json_type,
    )
    assert patched.status_code == 400, patched.text
    assert (
        a.get(f"{COLLECTIONS}/{smart['id']}").json()["definition"]
        == smart["definition"]
    )
    listed = a.get(COLLECTIONS)
    assert listed.status_code == 200
    assert [c["name"] for c in listed.json()] == ["Fine"]


def test_an_unknown_key_is_named_in_the_error(env: Env) -> None:
    """The 400 names the object's path and the unknown key."""
    response = env.as_(ALICE).post(
        COLLECTIONS,
        json={
            "name": "Extra",
            "definition": {"v": 1, "where": None, "note": "hello"},
        },
    )

    assert response.status_code == 400
    assert "'note'" in response.json()["detail"]


def test_a_stored_legacy_definition_still_lists_and_loads(env: Env) -> None:
    """A deep or oversized definition stored before the limits never gives a 500."""
    a = env.as_(ALICE)
    deep = env.smart(_where(_rating(">=", 1)), name="Deep")
    big = env.smart(_where(_rating(">=", 1)), name="Big")
    env.store_definition(deep["id"], _deep(800))
    env.store_definition(big["id"], {"v": 1, "junk": "x" * 100_000})

    listed = a.get(COLLECTIONS)
    assert listed.status_code == 200
    assert {c["name"] for c in listed.json()} == {"Deep", "Big"}
    for row in listed.json():
        assert row["definition"] is None
        assert row["item_count"] == 0
    for collection in (deep, big):
        fetched = a.get(f"{COLLECTIONS}/{collection['id']}")
        assert fetched.status_code == 200, fetched.text
        assert fetched.json()["warnings"] != []
        assert a.get(f"{COLLECTIONS}/{collection['id']}/count").json() == {"count": 0}
        renamed = a.patch(f"{COLLECTIONS}/{collection['id']}", json={"name": "Again"})
        assert renamed.status_code == 200, renamed.text


def test_a_manual_collection_given_a_malformed_definition_is_409(env: Env) -> None:
    """Whatever the definition holds, a manual collection answers 409."""
    a = env.as_(ALICE)
    shelf = a.post(COLLECTIONS, json={"name": "Shelf"}).json()
    for definition in ({}, {"v": 1}, {"v": 1, "note": "a\u0000b"}):
        response = a.patch(
            f"{COLLECTIONS}/{shelf['id']}", json={"definition": definition}
        )
        assert response.status_code == 409, response.text


def test_a_too_long_slug_is_400_never_500(env: Env) -> None:
    """The slug is limited to 120 characters on create and update."""
    a = env.as_(ALICE)
    shelf = a.post(COLLECTIONS, json={"name": "Shelf"}).json()
    too_long = "a" * 121

    assert (
        a.post(COLLECTIONS, json={"name": "Long", "slug": too_long}).status_code == 422
    )
    for slug in (too_long, "".join("ab12"[i % 4] for i in range(12_000))):
        patched = a.patch(f"{COLLECTIONS}/{shelf['id']}", json={"slug": slug})
        assert patched.status_code == 422, patched.text
    ok = a.patch(f"{COLLECTIONS}/{shelf['id']}", json={"slug": "a" * 120})
    assert ok.status_code == 200, ok.text
    assert len(ok.json()["slug"]) == 120
    assert a.get(f"{COLLECTIONS}/{'a' * 120}").status_code == 200


def test_a_slug_that_grows_when_normalised_is_400(env: Env) -> None:
    """A slug short enough raw but over the limit once normalised is a 400."""
    response = env.as_(ALICE).post(
        COLLECTIONS, json={"name": "Grows", "slug": "\u33a2" * 50}
    )

    assert response.status_code == 400, response.text


def test_the_list_can_be_limited_to_one_kind(env: Env) -> None:
    """`kind` returns only manual or only smart collections, for the caller only."""
    _films(env)
    a = env.as_(ALICE)
    a.post(COLLECTIONS, json={"name": "Shelf"})
    env.smart(_where(_rating(">=", 4)), name="Smart")
    env.as_(BOB)
    env.smart(_where(_rating(">=", 4)), name="Bob smart")
    b = env.as_(BOB)
    b.post(COLLECTIONS, json={"name": "Bob shelf"})
    a = env.as_(ALICE)

    def names(query: str) -> list[str]:
        response = a.get(f"{COLLECTIONS}{query}")
        assert response.status_code == 200, response.text
        return [c["name"] for c in response.json()]

    assert names("?kind=manual") == ["Shelf"]
    assert names("?kind=dynamic") == ["Smart"]
    assert names("") == ["Shelf", "Smart"]
    assert a.get(f"{COLLECTIONS}?kind=nope").status_code == 422


def _in(*ids: str) -> dict[str, Any]:
    return {"kind": "collection", "mode": "any", "in": list(ids)}


def test_a_smart_collection_can_be_built_on_another(env: Env) -> None:
    """`in collection <smart>` inlines its filter, narrowed by the new one."""
    _films(env)
    best = env.smart(_where(_rating(">=", 4)), name="Best")
    fav = {"kind": "favourite", "value": True}

    child = env.smart(_where(_in(best["id"]), fav), name="Best and loved")

    assert child["item_count"] == 1
    listed = env.as_(ALICE).get(f"{NODES}?collection={child['id']}")
    assert _names(listed) == {"Aliens"}


def test_saving_a_collection_that_refers_to_itself_is_a_400_naming_the_path(
    env: Env,
) -> None:
    """Directly and through another collection, the update is refused."""
    _films(env)
    first = env.smart(_where(_rating(">=", 4)), name="First")
    second = env.smart(_where(_in(first["id"])), name="Second")
    a = env.as_(ALICE)

    direct = a.patch(
        f"{COLLECTIONS}/{first['id']}", json={"definition": _where(_in(first["id"]))}
    )
    indirect = a.patch(
        f"{COLLECTIONS}/{first['id']}", json={"definition": _where(_in(second["id"]))}
    )

    for response in (direct, indirect):
        assert response.status_code == 400, response.text
        assert "refer to itself" in response.text
        assert "where.children[0].in[0]" in response.text
    unchanged = a.get(f"{COLLECTIONS}/{first['id']}")
    assert unchanged.json()["item_count"] == 3


def test_a_cycle_made_later_degrades_instead_of_failing(env: Env) -> None:
    """Rows that now form a loop read as empty, with warnings, never a 500."""
    _films(env)
    first = env.smart(_where(_rating(">=", 4)), name="First")
    second = env.smart(_where(_in(first["id"])), name="Second")
    env.store_definition(first["id"], _where(_in(second["id"])))
    a = env.as_(ALICE)

    listed = a.get(f"{NODES}?collection={second['id']}")
    shown = a.get(f"{COLLECTIONS}/{second['id']}")

    assert _names(listed) == set()
    assert shown.status_code == 200, shown.text
    assert shown.json()["item_count"] == 0
    assert shown.json()["warnings"]


def test_a_deleted_parent_makes_the_child_stale(env: Env) -> None:
    """Deleting the collection a search refers to leaves a warning and no matches."""
    _films(env)
    parent = env.smart(_where(_rating(">=", 4)), name="Parent")
    child = env.smart(_where(_in(parent["id"])), name="Child")
    a = env.as_(ALICE)
    assert a.get(f"{COLLECTIONS}/{child['id']}").json()["item_count"] == 3

    assert a.delete(f"{COLLECTIONS}/{parent['id']}").status_code == 204

    shown = a.get(f"{COLLECTIONS}/{child['id']}").json()
    assert shown["item_count"] == 0
    assert [w["message"] for w in shown["warnings"]] == [
        "That collection no longer exists."
    ]


def test_a_restored_parent_makes_the_child_evaluate_again(env: Env) -> None:
    """Restoring the collection a search refers to brings its matches back."""
    _films(env)
    parent = env.smart(_where(_rating(">=", 4)), name="Parent")
    child = env.smart(_where(_in(parent["id"])), name="Child")
    a = env.as_(ALICE)
    a.delete(f"{COLLECTIONS}/{parent['id']}")

    restored = a.post(f"{COLLECTIONS}/{parent['id']}/restore")

    assert restored.status_code == 200, restored.text
    assert restored.json()["item_count"] == 3
    shown = a.get(f"{COLLECTIONS}/{child['id']}").json()
    assert shown["item_count"] == 3
    assert shown["warnings"] == []


def test_a_purged_parent_leaves_the_child_with_a_warning_not_an_error(
    env: Env,
) -> None:
    """Purging the referred collection degrades the child like a deleted one."""
    _films(env)
    parent = env.smart(_where(_rating(">=", 4)), name="Parent")
    child = env.smart(_where(_in(parent["id"])), name="Child")
    a = env.as_(ALICE)
    a.delete(f"{COLLECTIONS}/{parent['id']}")

    assert a.delete(f"{COLLECTIONS}/{parent['id']}/purge").status_code == 204

    shown = a.get(f"{COLLECTIONS}/{child['id']}")
    assert shown.status_code == 200, shown.text
    assert shown.json()["item_count"] == 0
    assert [w["message"] for w in shown.json()["warnings"]] == [
        "That collection no longer exists."
    ]
    listed = a.get(f"{NODES}?collection={child['id']}")
    assert listed.status_code == 200
    assert listed.json() == []


def test_another_persons_collection_named_in_a_definition_is_stale(env: Env) -> None:
    """Bob cannot build on Alice's collection; it reads as one that is gone."""
    _films(env)
    alices = env.smart(_where(_rating(">=", 4)), name="Alice's")
    env.as_(BOB)

    mine = env.smart(_where(_in(alices["id"])), name="Bob's")
    ghost = env.smart(_where(_in(str(uuid.uuid7()))), name="Bob's ghost")

    assert mine["item_count"] == ghost["item_count"] == 0
    assert mine["warnings"] == ghost["warnings"]
    assert [w["message"] for w in mine["warnings"]] == [
        "That collection no longer exists."
    ]
