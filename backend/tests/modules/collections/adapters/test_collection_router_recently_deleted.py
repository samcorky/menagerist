"""Deleted-collection routes: list, restore and purge."""

import uuid
from typing import TYPE_CHECKING

import pytest
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.authorisation import TOKEN_GRANTABLE_PERMISSIONS
from app.entrypoints.api.shared.bridges.collection_items import get_item_lookup
from app.entrypoints.api.shared.dependencies import get_current_actor
from app.modules.collections.adapters.api.dependencies import (
    get_collections_repos,
    get_collections_uow,
)
from app.modules.collections.adapters.persistence.in_memory_collection_repository import (  # noqa: E501
    InMemoryCollectionRepository,
)
from app.modules.collections.adapters.persistence.in_memory_item_lookup import (
    InMemoryItemLookup,
)
from app.modules.collections.adapters.persistence.in_memory_membership_repository import (  # noqa: E501
    InMemoryMembershipRepository,
)
from app.modules.collections.adapters.persistence.unit_of_work import (
    create_in_memory_collections_uow,
)
from app.modules.collections.ports.unit_of_work import CollectionsRepos
from app.shared_kernel.actor import Actor

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI

BASE = "/api/v1/collection"
ALICE = uuid.UUID(int=101)
BOB = uuid.UUID(int=102)


class _World:
    def __init__(self, as_user: Callable[..., None]) -> None:
        self.app: FastAPI = create_app()
        collections = InMemoryCollectionRepository()
        self.repos = CollectionsRepos(
            collections=collections,
            memberships=InMemoryMembershipRepository(collections),
        )
        self.items = InMemoryItemLookup()
        self.app.dependency_overrides[get_collections_uow] = lambda: (
            create_in_memory_collections_uow(self.repos)
        )
        self.app.dependency_overrides[get_collections_repos] = lambda: self.repos
        self.app.dependency_overrides[get_item_lookup] = lambda: self.items
        self._as_user = as_user
        self.client = TestClient(self.app)

    def act_as(self, user_id: uuid.UUID) -> TestClient:
        self._as_user(self.app, user_id)
        return self.client


@pytest.fixture
def world(as_user: Callable[..., None]) -> _World:
    """A fresh app over in-memory collections, acting as Alice."""
    w = _World(as_user)
    w.act_as(ALICE)
    return w


def _create(client: TestClient, name: str = "Jazz") -> str:
    response = client.post(BASE, json={"name": name})
    assert response.status_code == 201
    return str(response.json()["id"])


def test_list_deleted_newest_first_with_total_and_paging(world: _World) -> None:
    """Rows carry id, name, kind and deleted_at; the Link header pages."""
    client = world.client
    assert client.get(f"{BASE}/deleted").json() == []
    ids = [_create(client, name) for name in ("One", "Two", "Three")]
    _create(client, "Live")
    for collection_id in ids:
        client.delete(f"{BASE}/{collection_id}")

    page = client.get(f"{BASE}/deleted", params={"limit": 2})
    after = page.headers["Link"].split("after=")[1].split(">")[0]
    rest = client.get(f"{BASE}/deleted", params={"limit": 2, "after": after})

    assert set(page.json()[0]) == {"id", "name", "kind", "deleted_at"}
    assert [r["id"] for r in page.json() + rest.json()] == ids[::-1]
    assert page.headers["Total-Count"] == "3"
    assert "Link" not in rest.headers


def test_restore_returns_the_collection_and_leaves_recently_deleted(
    world: _World,
) -> None:
    """The normal collection response comes back, with its items."""
    client = world.client
    shelf = _create(client)
    item = uuid.uuid7()
    world.items.add_owned(item, ALICE)
    client.put(f"{BASE}/{shelf}/item", json={"item_ids": [str(item)]})
    client.delete(f"{BASE}/{shelf}")

    response = client.post(f"{BASE}/{shelf}/restore")

    assert response.status_code == 200
    assert response.json()["id"] == shelf
    assert response.json()["item_count"] == 1
    assert client.get(f"{BASE}/deleted").json() == []


def test_restore_with_a_taken_slug_is_a_409_naming_it(world: _World) -> None:
    """A live collection holding the slug blocks the restore."""
    client = world.client
    gone = _create(client)
    client.delete(f"{BASE}/{gone}")
    _create(client)

    response = client.post(f"{BASE}/{gone}/restore")

    assert response.status_code == 409
    assert "'jazz'" in response.json()["detail"]
    assert len(client.get(f"{BASE}/deleted").json()) == 1


def test_purge_removes_it_for_good_and_only_from_recently_deleted(
    world: _World,
) -> None:
    """A live collection is a 404; a deleted one goes and cannot come back."""
    client = world.client
    shelf = _create(client)

    assert client.delete(f"{BASE}/{shelf}/purge").status_code == 404
    assert client.get(f"{BASE}/{shelf}").status_code == 200
    client.delete(f"{BASE}/{shelf}")
    assert client.delete(f"{BASE}/{shelf}/purge").status_code == 204
    assert client.get(f"{BASE}/deleted").json() == []
    assert client.post(f"{BASE}/{shelf}/restore").status_code == 404


def test_another_persons_deleted_content_is_invisible_and_untouchable(
    world: _World,
) -> None:
    """Bob sees, restores and purges nothing of Alice's."""
    shelf = _create(world.client)
    world.client.delete(f"{BASE}/{shelf}")

    bob = world.act_as(BOB)

    assert bob.get(f"{BASE}/deleted").json() == []
    assert bob.post(f"{BASE}/{shelf}/restore").status_code == 404
    assert bob.delete(f"{BASE}/{shelf}/purge").status_code == 404
    assert len(world.act_as(ALICE).get(f"{BASE}/deleted").json()) == 1


def test_a_token_can_restore_but_never_purge(world: _World) -> None:
    """Every grantable permission still does not reach the purge."""
    shelf = _create(world.client)
    world.client.delete(f"{BASE}/{shelf}")
    token = Actor(
        id=ALICE,
        roles=frozenset({"member"}),
        grants=frozenset(p.value for p in TOKEN_GRANTABLE_PERMISSIONS),
    )
    world.app.dependency_overrides[get_current_actor] = lambda: token

    assert world.client.delete(f"{BASE}/{shelf}/purge").status_code == 403
    assert world.client.post(f"{BASE}/{shelf}/restore").status_code == 200
