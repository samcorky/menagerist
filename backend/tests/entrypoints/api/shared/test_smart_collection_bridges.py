"""Smart collections through the real app and real bridges, for two people.

Each test runs over in-memory repositories and, integration-marked, on Postgres.
"""

import uuid
from typing import TYPE_CHECKING, Any

import pytest
import sqlalchemy
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
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
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.platform.database import get_engine, get_session_factory
from app.shared_kernel.actor import Actor

if TYPE_CHECKING:
    from collections.abc import Iterator

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

    def __init__(self, app: FastAPI, client: TestClient) -> None:
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


def _in_memory_app() -> FastAPI:
    app = create_app()
    graph = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )
    collections = build_in_memory_collections_repos()
    o = app.dependency_overrides
    o[get_graph_uow] = lambda: create_in_memory_graph_uow(graph)
    o[get_graph_repos] = lambda: graph
    o[get_collections_uow] = lambda: create_in_memory_collections_uow(collections)
    o[get_collections_repos] = lambda: collections
    o[get_item_lookup] = lambda: GraphItemLookup(graph)
    o[get_collection_members] = lambda: CollectionsMembers(collections)
    o[get_definition_checker] = lambda: GraphDefinitionChecker(graph)
    return app


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
        app = _in_memory_app()
        yield Env(app, TestClient(app))
        return
    request.getfixturevalue("postgres_url")
    sync_url: str = request.getfixturevalue("postgres_sync_url")
    get_session_factory.cache_clear()
    get_engine.cache_clear()
    try:
        app = create_app()
        with TestClient(app) as client:
            yield Env(app, client)
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
