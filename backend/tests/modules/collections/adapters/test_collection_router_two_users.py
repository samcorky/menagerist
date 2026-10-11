"""Collection routes with two signed-in people: nothing leaks across."""

import uuid
from typing import TYPE_CHECKING

import pytest
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.collection_items import get_item_lookup
from app.entrypoints.api.shared.collection_members import get_collection_members
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
    """A fresh app over in-memory collections."""
    return _World(as_user)


def _create(client: TestClient, name: str = "Jazz") -> dict[str, str]:
    response = client.post(BASE, json={"name": name})
    assert response.status_code == 201
    body: dict[str, str] = response.json()
    return body


def test_other_user_gets_404_on_every_collection_route(world: _World) -> None:
    """B cannot read, change, delete or add to A collection."""
    shelf = _create(world.act_as(ALICE))
    url = f"{BASE}/{shelf['id']}"
    item = uuid.uuid7()
    world.items.add_owned(item, BOB)
    bob = world.act_as(BOB)

    assert bob.get(url).status_code == 404
    assert bob.patch(url, json={"name": "Mine"}).status_code == 404
    assert bob.put(f"{url}/item", json={"item_ids": [str(item)]}).status_code == 404
    assert bob.delete(f"{url}/item/{item}").status_code == 404
    assert bob.delete(url).status_code == 404
    assert world.act_as(ALICE).get(url).json()["name"] == "Jazz"


def test_list_shows_only_own_collections(world: _World) -> None:
    """Each person lists only what they own."""
    _create(world.act_as(ALICE), "A one")
    _create(world.act_as(BOB), "B one")

    assert [c["name"] for c in world.act_as(ALICE).get(BASE).json()] == ["A one"]
    assert [c["name"] for c in world.act_as(BOB).get(BASE).json()] == ["B one"]


def test_same_name_gets_the_same_slug_for_both_people(world: _World) -> None:
    """Slug suffixes are independent per owner."""
    first = _create(world.act_as(ALICE))
    other = _create(world.act_as(BOB))
    again = _create(world.act_as(ALICE))

    assert (first["slug"], other["slug"], again["slug"]) == ("jazz", "jazz", "jazz-2")
    taken = world.act_as(ALICE).post(BASE, json={"name": "X", "slug": "jazz"})
    assert taken.status_code == 409
    assert (
        world.act_as(BOB).post(BASE, json={"name": "X", "slug": "x"}).status_code == 201
    )


def test_adding_an_item_of_someone_else_is_rejected(world: _World) -> None:
    """B naming an item of A on B own collection fails like an unknown id."""
    shelf = _create(world.act_as(BOB))
    theirs = uuid.uuid7()
    world.items.add_owned(theirs, ALICE)

    response = world.act_as(BOB).put(
        f"{BASE}/{shelf['id']}/item", json={"item_ids": [str(theirs)]}
    )

    assert response.status_code == 400
    assert str(theirs) in response.json()["detail"]


def test_item_count_and_etag_use_the_visible_count(world: _World) -> None:
    """The ETag follows the count the viewer can see."""
    shelf = _create(world.act_as(ALICE))
    url = f"{BASE}/{shelf['id']}"
    mine = uuid.uuid7()
    world.items.add_owned(mine, ALICE)
    client = world.act_as(ALICE)
    client.put(f"{url}/item", json={"item_ids": [str(mine)]})
    hidden = uuid.uuid7()
    world.items.live.add(hidden)
    client.put(f"{url}/item", json={"item_ids": [str(hidden)]})
    before = client.get(url)
    world.items.live.discard(hidden)
    world.items.add_owned(hidden, BOB)
    after = client.get(url)

    assert before.json()["item_count"] == 2
    assert after.json()["item_count"] == 1
    assert before.headers["ETag"] != after.headers["ETag"]
    # B holds the ETag of A but gets a 404, not a 304.
    stale = world.act_as(BOB).get(
        url, headers={"If-None-Match": before.headers["ETag"]}
    )
    assert stale.status_code == 404


def test_items_in_collection_filter_is_404_for_other_people(
    as_user: Callable[..., None],
) -> None:
    """GET /node?collection=<A collection> as B is a 404."""
    app = create_app()
    graph = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )
    members = InMemoryCollectionMembers()
    collection_id = uuid.uuid7()
    members.add_collection(collection_id, [], owner_id=ALICE)
    app.dependency_overrides[get_graph_uow] = lambda: create_in_memory_graph_uow(graph)
    app.dependency_overrides[get_graph_repos] = lambda: graph
    app.dependency_overrides[get_collection_members] = lambda: members
    client = TestClient(app)

    as_user(app, ALICE)
    assert client.get(f"/api/v1/node?collection={collection_id}").status_code == 200
    as_user(app, BOB)
    assert client.get(f"/api/v1/node?collection={collection_id}").status_code == 404
