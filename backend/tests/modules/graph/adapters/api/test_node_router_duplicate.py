"""POST /nodes/{id}/duplicate."""

import uuid
from typing import TYPE_CHECKING

import pytest
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.bridges.collection_members import get_collection_members
from app.entrypoints.api.shared.bridges.item_companions import get_item_companions
from app.modules.graph.adapters.api.dependencies import get_graph_repos, get_graph_uow
from app.modules.graph.adapters.persistence.in_memory_collection_members import (
    InMemoryCollectionMembers,
)
from app.modules.graph.adapters.persistence.unit_of_work import (
    build_in_memory_graph_repos,
    create_in_memory_graph_uow,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI

    from app.modules.graph.ports.unit_of_work import GraphRepos
    from app.shared_kernel.actor import Actor

BASE = "/api/v1/nodes"
ALICE = uuid.UUID(int=101)
BOB = uuid.UUID(int=102)


class _Companions:
    def __init__(self) -> None:
        self.media: list[tuple[uuid.UUID, uuid.UUID, bool, bool]] = []
        self.collections: list[tuple[uuid.UUID, uuid.UUID]] = []

    async def copy_media(
        self,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        *,
        attachments: bool,
        cover: bool,
        actor: Actor,
    ) -> None:
        self.media.append((source_id, target_id, attachments, cover))

    async def copy_collections(
        self, source_id: uuid.UUID, target_id: uuid.UUID, *, actor: Actor
    ) -> None:
        self.collections.append((source_id, target_id))


class _World:
    def __init__(self, as_user: Callable[..., None]) -> None:
        self.app: FastAPI = create_app()
        self.repos: GraphRepos = build_in_memory_graph_repos()
        self.companions = _Companions()
        overrides = self.app.dependency_overrides
        overrides[get_graph_uow] = lambda: create_in_memory_graph_uow(self.repos)
        overrides[get_graph_repos] = lambda: self.repos
        overrides[get_collection_members] = lambda: InMemoryCollectionMembers()
        overrides[get_item_companions] = lambda: self.companions
        self._as_user = as_user
        self.client = TestClient(self.app)

    def act_as(self, user_id: uuid.UUID) -> TestClient:
        self._as_user(self.app, user_id)
        return self.client

    def create(self, name: str, **fields: object) -> str:
        response = self.client.post(BASE, json={"name": name, **fields})
        assert response.status_code == 201
        return str(response.json()["id"])


@pytest.fixture
def world(as_user: Callable[..., None]) -> _World:
    """A fresh app over in-memory repositories, acting as Alice."""
    w = _World(as_user)
    w.act_as(ALICE)
    return w


def test_duplicate_returns_201_with_a_new_copy(world: _World) -> None:
    """The copy has the original's content under the requested name."""
    source = world.create(
        "Alien",
        type="film",
        description="Sci-fi horror",
        attributes={"year": 1979},
        tags=["classic"],
    )

    response = world.client.post(f"{BASE}/{source}/duplicate", json={"name": "Alien 2"})

    assert response.status_code == 201
    body = response.json()
    assert body["id"] != source
    assert body["name"] == "Alien 2"
    assert body["type"] == "film"
    assert body["description"] == "Sci-fi horror"
    assert body["attributes"] == {"year": 1979}
    assert body["tags"] == ["classic"]
    assert body["favourite"] is False
    assert world.client.get(f"{BASE}/{source}").json()["name"] == "Alien"
    assert world.client.get(f"{BASE}/{body['id']}").status_code == 200


def test_duplicate_defaults_copy_only_collections(world: _World) -> None:
    """With no flags set, collections are copied and media, cover and links are not."""
    source = world.create("Alien")

    response = world.client.post(f"{BASE}/{source}/duplicate", json={"name": "Copy"})

    copy = uuid.UUID(response.json()["id"])
    assert world.companions.collections == [(uuid.UUID(source), copy)]
    assert world.companions.media == []


def test_duplicate_passes_each_choice_on(world: _World) -> None:
    """Media and cover reach the companions as separate choices."""
    source = world.create("Alien")

    response = world.client.post(
        f"{BASE}/{source}/duplicate",
        json={
            "name": "Copy",
            "copy_media": True,
            "copy_cover": False,
            "copy_collections": False,
        },
    )

    copy = uuid.UUID(response.json()["id"])
    assert world.companions.media == [(uuid.UUID(source), copy, True, False)]
    assert world.companions.collections == []


def test_duplicate_can_copy_connections(world: _World) -> None:
    """Connections to other items are repeated on the copy when asked for."""
    source = world.create("Alien")
    other = world.create("Ridley Scott")
    edge = world.client.post(
        "/api/v1/edges",
        json={"source_id": source, "target_id": other, "type": "directed-by"},
    )
    assert edge.status_code == 201

    response = world.client.post(
        f"{BASE}/{source}/duplicate",
        json={"name": "Copy", "copy_relationships": True},
    )

    copy = response.json()["id"]
    edges = world.client.get("/api/v1/edges", params={"node_id": copy}).json()
    assert [(e["source_id"], e["target_id"]) for e in edges] == [(copy, other)]


def test_duplicate_of_an_unknown_item_is_404(world: _World) -> None:
    """A missing item is reported as not found."""
    response = world.client.post(
        f"{BASE}/{uuid.uuid7()}/duplicate", json={"name": "Copy"}
    )

    assert response.status_code == 404


def test_duplicate_needs_a_name(world: _World) -> None:
    """The request body must carry the copy's name."""
    source = world.create("Alien")

    response = world.client.post(f"{BASE}/{source}/duplicate", json={})

    assert response.status_code == 422


def test_duplicate_of_a_blank_name_is_refused(world: _World) -> None:
    """A whitespace-only name fails the item's own rule."""
    source = world.create("Alien")

    response = world.client.post(f"{BASE}/{source}/duplicate", json={"name": "  "})

    assert response.status_code == 400


def test_another_user_cannot_duplicate_the_item(world: _World) -> None:
    """Someone else's item looks missing, and nothing is created for them."""
    source = world.create("Alien")
    bob = world.act_as(BOB)

    response = bob.post(f"{BASE}/{source}/duplicate", json={"name": "Stolen"})

    assert response.status_code == 404
    assert bob.get(BASE).json() == []
    assert world.companions.collections == []
