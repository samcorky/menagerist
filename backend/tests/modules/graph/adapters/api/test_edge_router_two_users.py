"""Connection and type routes with several signed-in people: nothing leaks across."""

import uuid
from typing import TYPE_CHECKING

import pytest
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.collection_members import get_collection_members
from app.modules.graph.adapters.api.dependencies import get_graph_repos, get_graph_uow
from app.modules.graph.adapters.persistence.in_memory_collection_members import (
    InMemoryCollectionMembers,
)
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

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI

ALICE = uuid.UUID(int=101)
BOB = uuid.UUID(int=102)
ADMIN = uuid.UUID(int=100)


class _World:
    """One app, with helpers to act as any person."""

    def __init__(self, as_user: Callable[..., None]) -> None:
        self.app: FastAPI = create_app()
        repos = GraphRepos(
            nodes=InMemoryNodeRepository(),
            edges=InMemoryEdgeRepository(),
            node_types=InMemoryNodeTypeRepository(),
            edge_types=InMemoryEdgeTypeRepository(),
        )
        self.app.dependency_overrides[get_graph_uow] = lambda: (
            create_in_memory_graph_uow(repos)
        )
        self.app.dependency_overrides[get_graph_repos] = lambda: repos
        self.app.dependency_overrides[get_collection_members] = lambda: (
            InMemoryCollectionMembers()
        )
        self._as_user = as_user
        self.client = TestClient(self.app)

    def act_as(self, user_id: uuid.UUID, role: str = "member") -> TestClient:
        self._as_user(self.app, user_id, role)
        return self.client


@pytest.fixture
def world(as_user: Callable[..., None]) -> _World:
    """A fresh app wired to in-memory repositories."""
    return _World(as_user)


def _item(client: TestClient, name: str) -> str:
    response = client.post("/api/v1/node", json={"name": name})
    assert response.status_code == 201
    return str(response.json()["id"])


def _connect(
    client: TestClient, type_: str = "owns", **extra: object
) -> dict[str, str]:
    source, target = _item(client, "a"), _item(client, "b")
    response = client.post(
        "/api/v1/edge",
        json={"source_id": source, "target_id": target, "type": type_, **extra},
    )
    assert response.status_code == 201
    created: dict[str, str] = response.json()
    return created


def test_other_users_connection_is_404_on_get_patch_delete(world: _World) -> None:
    """Someone else's connection answers 404 on every single-connection route."""
    edge = _connect(world.act_as(ALICE))
    url = f"/api/v1/edge/{edge['id']}"

    bob = world.act_as(BOB)
    assert bob.get(url).status_code == 404
    assert bob.patch(url, json={"attributes": {"k": "v"}}).status_code == 404
    assert bob.delete(url).status_code == 404

    alice = world.act_as(ALICE)
    assert alice.get(url).status_code == 200


def test_other_users_connections_never_appear_in_lists(world: _World) -> None:
    """The list, with or without a node filter, only covers the caller's own."""
    alice = world.act_as(ALICE)
    edge = _connect(alice)

    bob = world.act_as(BOB)
    assert bob.get("/api/v1/edge").json() == []
    assert bob.get("/api/v1/edge", params={"node_id": edge["source_id"]}).json() == []
    assert "Link" not in bob.get("/api/v1/edge").headers

    alice = world.act_as(ALICE)
    assert [e["id"] for e in alice.get("/api/v1/edge").json()] == [edge["id"]]


def test_pagination_link_ignores_other_users_connections(world: _World) -> None:
    """Paging through your own connections is unaffected by anyone else's."""
    alice = world.act_as(ALICE)
    mine = [_connect(alice) for _ in range(3)]
    bob = world.act_as(BOB)
    _connect(bob)
    _connect(bob)

    alice = world.act_as(ALICE)
    first = alice.get("/api/v1/edge", params={"limit": 2})
    assert len(first.json()) == 2
    assert "Link" in first.headers
    rest = alice.get("/api/v1/edge", params={"after": first.json()[-1]["id"]})
    assert {e["id"] for e in [*first.json(), *rest.json()]} == {e["id"] for e in mine}


def test_connecting_to_someone_elses_item_is_404(world: _World) -> None:
    """Both endpoints must be yours, on the single and batch routes."""
    alice = world.act_as(ALICE)
    mine = _item(alice, "mine")
    bob = world.act_as(BOB)
    theirs = _item(bob, "theirs")

    alice = world.act_as(ALICE)
    for source, target in ((mine, theirs), (theirs, mine)):
        single = alice.post(
            "/api/v1/edge",
            json={"source_id": source, "target_id": target, "type": "owns"},
        )
        assert single.status_code == 404
    batch = alice.post(
        "/api/v1/edge/batch",
        json={"source_id": mine, "target_ids": [theirs], "type": "owns"},
    )
    assert batch.status_code == 404
    assert alice.get("/api/v1/edge").json() == []
    assert alice.get("/api/v1/edge-type").json() == []


def test_etag_of_someone_elses_connection_does_not_leak(world: _World) -> None:
    """A conditional GET with another person's ETag is a 404, never a 304."""
    edge = _connect(world.act_as(ALICE))
    url = f"/api/v1/edge/{edge['id']}"
    etag = world.act_as(ALICE).get(url).headers["ETag"]
    assert (
        world.act_as(ALICE).get(url, headers={"If-None-Match": etag}).status_code == 304
    )

    probe = world.act_as(BOB).get(url, headers={"If-None-Match": etag})

    assert probe.status_code == 404
    assert "ETag" not in probe.headers


def test_patch_with_if_match_of_someone_elses_connection_is_404(
    world: _World,
) -> None:
    """A guarded PATCH on another person's connection is a 404, not a 412."""
    edge = _connect(world.act_as(ALICE))
    url = f"/api/v1/edge/{edge['id']}"
    etag = world.act_as(ALICE).get(url).headers["ETag"]

    response = world.act_as(BOB).patch(
        url, json={"attributes": {}}, headers={"If-Match": etag}
    )

    assert response.status_code == 404


def test_edge_type_usage_counts_are_per_person(world: _World) -> None:
    """Attribute usage only reflects the caller's own connections."""
    alice = world.act_as(ALICE)
    _connect(alice, attributes={"note": "x"})
    edge_type = alice.get("/api/v1/edge-type").json()[0]
    bob = world.act_as(BOB)
    _connect(bob, attributes={"note": "x"})
    _connect(bob, attributes={"note": "y"})
    url = f"/api/v1/edge-type/{edge_type['id']}/attribute/note/usage"

    assert world.act_as(ALICE).get(url).json() == {"count": 1}
    assert world.act_as(BOB).get(url).json() == {"count": 2}


def test_members_get_403_on_admin_only_structure_routes(world: _World) -> None:
    """Deleting a type and purging an attribute are refused for members."""
    alice = world.act_as(ALICE)
    node_type = alice.post(
        "/api/v1/node-type", json={"slug": "film", "label": "Film"}
    ).json()
    _connect(alice, attributes={"note": "x"})
    edge_type = alice.get("/api/v1/edge-type").json()[0]

    requests = [
        ("delete", f"/api/v1/node-type/{node_type['id']}"),
        ("delete", f"/api/v1/node-type/{node_type['id']}/attribute/x"),
        ("delete", f"/api/v1/edge-type/{edge_type['id']}"),
        ("delete", f"/api/v1/edge-type/{edge_type['id']}/attribute/note"),
    ]
    for method, url in requests:
        assert getattr(alice, method)(url).status_code == 403

    assert alice.get(f"/api/v1/edge-type/{edge_type['id']}").status_code == 200
    assert alice.get(f"/api/v1/node-type/{node_type['id']}").status_code == 200


def test_admin_purge_and_delete_span_all_users_content(world: _World) -> None:
    """An admin's purge touches everyone's connections and items."""
    alice = world.act_as(ALICE)
    _connect(alice, attributes={"note": "x"})
    edge_type = alice.get("/api/v1/edge-type").json()[0]
    bob = world.act_as(BOB)
    _connect(bob, attributes={"note": "x"})
    node_type = bob.post(
        "/api/v1/node-type", json={"slug": "film", "label": "Film"}
    ).json()
    bob.post("/api/v1/node", json={"name": "Alien", "type": "film"})
    alice = world.act_as(ALICE)
    alice.post("/api/v1/node", json={"name": "Aliens", "type": "film"})

    admin = world.act_as(ADMIN, "admin")
    purge = admin.delete(f"/api/v1/edge-type/{edge_type['id']}/attribute/note")
    assert purge.status_code == 204
    assert purge.content == b""
    blocked = admin.delete(f"/api/v1/edge-type/{edge_type['id']}")
    assert blocked.status_code == 409
    assert admin.delete(f"/api/v1/node-type/{node_type['id']}").status_code == 204

    for person in (ALICE, BOB):
        client = world.act_as(person)
        assert all(e["attributes"] == {} for e in client.get("/api/v1/edge").json())
        assert {n["type"] for n in client.get("/api/v1/node").json() if n["name"]} == {
            None
        }
