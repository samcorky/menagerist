"""Deleted-item routes: list, restore and purge."""

import asyncio
import uuid
from typing import TYPE_CHECKING

import pytest
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.authorisation import TOKEN_GRANTABLE_PERMISSIONS
from app.entrypoints.api.shared.bridges.collection_members import get_collection_members
from app.entrypoints.api.shared.bridges.item_dependents import get_item_dependents
from app.entrypoints.api.shared.dependencies import get_current_actor
from app.modules.graph.adapters.api.dependencies import get_graph_repos, get_graph_uow
from app.modules.graph.adapters.persistence.in_memory_collection_members import (
    InMemoryCollectionMembers,
)
from app.modules.graph.adapters.persistence.unit_of_work import (
    build_in_memory_graph_repos,
    create_in_memory_graph_uow,
)
from app.shared_kernel.actor import Actor

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI

    from app.modules.graph.ports.unit_of_work import GraphRepos

BASE = "/api/v1/node"
ALICE = uuid.UUID(int=101)
BOB = uuid.UUID(int=102)


class _Dependents:
    def __init__(self) -> None:
        self.purged: list[uuid.UUID] = []

    async def purge_for_item(self, item_id: uuid.UUID) -> None:
        self.purged.append(item_id)


async def _delete_type(repos: GraphRepos, slug: str) -> None:
    node_type = await repos.node_types.get_by_slug(slug)
    assert node_type is not None
    node_type.soft_delete()
    await repos.node_types.save(node_type)


class _World:
    def __init__(self, as_user: Callable[..., None]) -> None:
        self.app: FastAPI = create_app()
        self.repos: GraphRepos = build_in_memory_graph_repos()
        self.dependents = _Dependents()
        overrides = self.app.dependency_overrides
        overrides[get_graph_uow] = lambda: create_in_memory_graph_uow(self.repos)
        overrides[get_graph_repos] = lambda: self.repos
        overrides[get_collection_members] = lambda: InMemoryCollectionMembers()
        overrides[get_item_dependents] = lambda: self.dependents
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


def test_list_deleted_is_empty_then_shows_deleted_items_newest_first(
    world: _World,
) -> None:
    """Rows carry id, name, type and deleted_at; Total-Count is exact."""
    client = world.client
    assert client.get(f"{BASE}/deleted").json() == []
    first = world.create("Alien", type=None)
    second = world.create("Aliens")
    world.create("Live")
    client.delete(f"{BASE}/{first}")
    client.delete(f"{BASE}/{second}")

    response = client.get(f"{BASE}/deleted")

    body = response.json()
    assert [row["id"] for row in body] == [second, first]
    assert set(body[0]) == {"id", "name", "type", "deleted_at"}
    assert response.headers["Total-Count"] == "2"
    assert "Link" not in response.headers


def test_list_deleted_pages_with_a_link_header(world: _World) -> None:
    """The Link header carries `after`; following it gives the rest."""
    client = world.client
    ids = [world.create(str(i)) for i in range(3)]
    for item_id in ids:
        client.delete(f"{BASE}/{item_id}")

    page = client.get(f"{BASE}/deleted", params={"limit": 2})
    link = page.headers["Link"]
    after = link.split("after=")[1].split(">")[0]
    rest = client.get(f"{BASE}/deleted", params={"limit": 2, "after": after})

    assert len(page.json()) == 2
    assert [r["id"] for r in page.json() + rest.json()] == ids[::-1]
    assert page.headers["Total-Count"] == "3"


def test_deleted_is_not_read_as_an_item_id(world: _World) -> None:
    """The fixed path wins over `/{node_id}`."""
    assert world.client.get(f"{BASE}/deleted").status_code == 200


def test_restore_brings_the_item_back(world: _World) -> None:
    """The item answers GET again and leaves Recently deleted."""
    client = world.client
    item = world.create("Alien")
    client.delete(f"{BASE}/{item}")
    assert client.get(f"{BASE}/{item}").status_code == 404

    response = client.post(f"{BASE}/{item}/restore")

    assert response.status_code == 200
    assert response.json()["id"] == item
    assert client.get(f"{BASE}/{item}").status_code == 200
    assert client.get(f"{BASE}/deleted").json() == []


def test_restore_a_live_or_unknown_item_is_404(world: _World) -> None:
    """Only deleted items can be restored."""
    item = world.create("Alien")

    assert world.client.post(f"{BASE}/{item}/restore").status_code == 404
    assert world.client.post(f"{BASE}/{uuid.uuid7()}/restore").status_code == 404


def test_restore_when_the_type_was_deleted_is_a_409(world: _World) -> None:
    """The problem names the slug."""
    client = world.client
    client.post("/api/v1/node-type", json={"slug": "film", "label": "Film"})
    item = world.create("Alien", type="film")
    client.delete(f"{BASE}/{item}")
    asyncio.run(_delete_type(world.repos, "film"))

    response = client.post(f"{BASE}/{item}/restore")

    assert response.status_code == 409
    assert "film" in response.json()["detail"]


def test_purge_removes_the_item_for_good(world: _World) -> None:
    """204, the dependents are purged, and the item is in no list at all."""
    client = world.client
    item = world.create("Alien")
    client.delete(f"{BASE}/{item}")

    response = client.delete(f"{BASE}/{item}/purge")

    assert response.status_code == 204
    assert world.dependents.purged == [uuid.UUID(item)]
    assert client.get(f"{BASE}/deleted").json() == []
    assert client.post(f"{BASE}/{item}/restore").status_code == 404


def test_purge_a_live_item_is_404_and_nothing_is_removed(world: _World) -> None:
    """A live item is never purged."""
    item = world.create("Alien")

    assert world.client.delete(f"{BASE}/{item}/purge").status_code == 404
    assert world.dependents.purged == []
    assert world.client.get(f"{BASE}/{item}").status_code == 200


def test_another_persons_deleted_content_is_invisible_and_untouchable(
    world: _World,
) -> None:
    """Bob sees nothing of Alice's deleted content and cannot restore or purge it."""
    item = world.create("Alien")
    world.client.delete(f"{BASE}/{item}")

    bob = world.act_as(BOB)

    assert bob.get(f"{BASE}/deleted").json() == []
    assert bob.get(f"{BASE}/deleted").headers["Total-Count"] == "0"
    assert bob.post(f"{BASE}/{item}/restore").status_code == 404
    assert bob.delete(f"{BASE}/{item}/purge").status_code == 404
    assert world.dependents.purged == []
    alice = world.act_as(ALICE)
    assert len(alice.get(f"{BASE}/deleted").json()) == 1


def test_a_token_can_restore_but_never_purge(world: _World) -> None:
    """Every grantable permission still does not reach `graph:item:purge`."""
    item = world.create("Alien")
    world.client.delete(f"{BASE}/{item}")
    token = Actor(
        id=ALICE,
        roles=frozenset({"member"}),
        grants=frozenset(p.value for p in TOKEN_GRANTABLE_PERMISSIONS),
    )
    world.app.dependency_overrides[get_current_actor] = lambda: token

    assert world.client.delete(f"{BASE}/{item}/purge").status_code == 403
    assert world.client.get(f"{BASE}/deleted").status_code == 200
    assert world.client.post(f"{BASE}/{item}/restore").status_code == 200
    assert world.dependents.purged == []
