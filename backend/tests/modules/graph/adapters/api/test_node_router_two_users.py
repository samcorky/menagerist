"""Item and item-type routes with two signed-in people: nothing leaks across."""

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


class _World:
    """One app, with helpers to act as either person."""

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

    def act_as(self, user_id: uuid.UUID) -> TestClient:
        self._as_user(self.app, user_id)
        return self.client


@pytest.fixture
def world(as_user: Callable[..., None]) -> _World:
    """A fresh app wired to in-memory repositories."""
    return _World(as_user)


def _create(client: TestClient, **fields: object) -> dict[str, object]:
    response = client.post("/api/v1/node", json=fields)
    assert response.status_code == 201
    created: dict[str, object] = response.json()
    return created


def test_other_users_item_is_404_on_get_patch_delete_and_promote(
    world: _World,
) -> None:
    """Someone else's item answers 404 on every single-item route."""
    alice = world.act_as(ALICE)
    node_type = alice.post(
        "/api/v1/node-type", json={"slug": "film", "label": "Film"}
    ).json()
    node = _create(alice, name="Alien", type="film")
    url = f"/api/v1/node/{node['id']}"

    bob = world.act_as(BOB)

    assert bob.get(url).status_code == 404
    assert bob.patch(url, json={"name": "Stolen"}).status_code == 404
    assert bob.delete(url).status_code == 404
    promote = bob.post(
        f"{url}/attribute/x/promote", json={"node_type_id": node_type["id"]}
    )
    assert promote.status_code == 404

    alice = world.act_as(ALICE)
    still_there = alice.get(url)
    assert still_there.status_code == 200
    assert still_there.json()["name"] == "Alien"


def test_other_users_items_never_appear_in_lists_search_or_counts(
    world: _World,
) -> None:
    """Lists, `q` search and Total-Count only cover the caller's own items."""
    alice = world.act_as(ALICE)
    _create(alice, name="Alien", type="film", attributes={"note": "xenomorph"})
    _create(alice, name="Aliens", type="film")

    bob = world.act_as(BOB)
    empty = bob.get("/api/v1/node")
    searched = bob.get("/api/v1/node", params={"q": "alien"})
    by_attribute = bob.get("/api/v1/node", params={"q": "xenomorph"})
    typed = bob.get("/api/v1/node", params={"type": "film"})

    for response in (empty, searched, by_attribute, typed):
        assert response.status_code == 200
        assert response.json() == []
        assert response.headers["Total-Count"] == "0"
        assert "Link" not in response.headers

    alice = world.act_as(ALICE)
    mine = alice.get("/api/v1/node", params={"q": "alien"})
    assert len(mine.json()) == 2
    assert mine.headers["Total-Count"] == "2"


def test_pagination_link_and_total_do_not_count_other_users_items(
    world: _World,
) -> None:
    """A page boundary is computed over the caller's items alone."""
    for i in range(3):
        _create(world.act_as(ALICE), name=f"A{i}")
        _create(world.act_as(BOB), name=f"B{i}")

    alice = world.act_as(ALICE)
    full = alice.get("/api/v1/node", params={"limit": 3})
    split = alice.get("/api/v1/node", params={"limit": 2})

    assert full.headers["Total-Count"] == "3"
    assert "Link" not in full.headers
    assert {n["name"] for n in full.json()} == {"A0", "A1", "A2"}
    assert split.headers["Total-Count"] == "3"
    assert "Link" in split.headers
    assert len(split.json()) == 2


def test_etag_of_someone_elses_item_does_not_leak(world: _World) -> None:
    """A conditional GET with another person's ETag is a 404, never a 304."""
    alice = world.act_as(ALICE)
    node = _create(alice, name="Alien")
    url = f"/api/v1/node/{node['id']}"
    etag = alice.get(url).headers["ETag"]
    assert alice.get(url, headers={"If-None-Match": etag}).status_code == 304

    bob = world.act_as(BOB)
    probe = bob.get(url, headers={"If-None-Match": etag})

    assert probe.status_code == 404
    assert "ETag" not in probe.headers


def test_patch_with_if_match_of_someone_elses_item_is_404(world: _World) -> None:
    """A guarded PATCH on another person's item is a 404, not a 412."""
    alice = world.act_as(ALICE)
    node = _create(alice, name="Alien")
    url = f"/api/v1/node/{node['id']}"
    etag = alice.get(url).headers["ETag"]

    bob = world.act_as(BOB)
    response = bob.patch(url, json={"name": "Stolen"}, headers={"If-Match": etag})

    assert response.status_code == 404


def test_usage_counts_and_value_suggestions_are_per_person(world: _World) -> None:
    """Attribute usage and suggestions only reflect the caller's own items."""
    alice = world.act_as(ALICE)
    node_type = alice.post(
        "/api/v1/node-type", json={"slug": "film", "label": "Film"}
    ).json()
    _create(alice, name="Alien", type="film", attributes={"rating": "R"})
    base = f"/api/v1/node-type/{node_type['id']}/attribute/rating"

    assert alice.get(f"{base}/usage").json() == {"count": 1}
    assert alice.get(f"{base}/values").json() == [{"value": "R", "count": 1}]

    bob = world.act_as(BOB)
    assert bob.get(f"/api/v1/node-type/{node_type['id']}").status_code == 200
    assert bob.get(f"{base}/usage").json() == {"count": 0}
    assert bob.get(f"{base}/values").json() == []
