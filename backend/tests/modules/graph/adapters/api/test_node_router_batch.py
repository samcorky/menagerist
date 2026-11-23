"""POST /nodes/delete and POST /nodes/tags."""

import uuid
from typing import TYPE_CHECKING

import pytest
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.modules.graph.adapters.api.dependencies import get_graph_repos, get_graph_uow
from app.modules.graph.adapters.persistence.unit_of_work import (
    build_in_memory_graph_repos,
    create_in_memory_graph_uow,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI

    from app.modules.graph.ports.unit_of_work import GraphRepos

BASE = "/api/v1/nodes"
ALICE = uuid.UUID(int=101)
BOB = uuid.UUID(int=102)


class _World:
    def __init__(self, as_user: Callable[..., None]) -> None:
        self.app: FastAPI = create_app()
        self.repos: GraphRepos = build_in_memory_graph_repos()
        self.app.dependency_overrides[get_graph_uow] = lambda: (
            create_in_memory_graph_uow(self.repos)
        )
        self.app.dependency_overrides[get_graph_repos] = lambda: self.repos
        self._as_user = as_user
        self.client = TestClient(self.app)

    def act_as(self, user_id: uuid.UUID) -> None:
        self._as_user(self.app, user_id)

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


def test_delete_returns_204_and_removes_every_item(world: _World) -> None:
    """Delete returns 204 and removes every item."""
    ids = [world.create(n) for n in ("a", "b")]

    response = world.client.post(f"{BASE}/delete", json={"ids": ids})

    assert response.status_code == 204
    assert [world.client.get(f"{BASE}/{i}").status_code for i in ids] == [404, 404]


def test_delete_with_an_unknown_id_is_400_and_deletes_nothing(world: _World) -> None:
    """Delete with an unknown id is 400 and deletes nothing."""
    kept = world.create("a")
    ghost = str(uuid.uuid4())

    response = world.client.post(f"{BASE}/delete", json={"ids": [kept, ghost]})

    assert response.status_code == 400
    assert ghost in response.json()["detail"]
    assert world.client.get(f"{BASE}/{kept}").status_code == 200


def test_delete_with_no_ids_is_400(world: _World) -> None:
    """Delete with no ids is 400."""
    assert world.client.post(f"{BASE}/delete", json={"ids": []}).status_code == 400


def test_delete_refuses_another_accounts_item(world: _World) -> None:
    """Delete refuses another accounts item."""
    world.act_as(BOB)
    theirs = world.create("bob's")
    world.act_as(ALICE)
    mine = world.create("mine")

    response = world.client.post(f"{BASE}/delete", json={"ids": [mine, theirs]})

    assert response.status_code in {400, 403, 404}
    assert world.client.get(f"{BASE}/{mine}").status_code == 200


def test_tags_returns_how_many_items_changed(world: _World) -> None:
    """Tags returns how many items changed."""
    a = world.create("a", tags=["x"])
    b = world.create("b")

    response = world.client.post(
        f"{BASE}/tags", json={"ids": [a, b], "add": ["x"], "remove": []}
    )

    assert response.status_code == 200
    assert response.json() == {"changed": 1}
    assert world.client.get(f"{BASE}/{b}").json()["tags"] == ["x"]


def test_tags_with_nothing_to_change_is_400(world: _World) -> None:
    """Tags with nothing to change is 400."""
    a = world.create("a")

    response = world.client.post(f"{BASE}/tags", json={"ids": [a]})

    assert response.status_code == 400
