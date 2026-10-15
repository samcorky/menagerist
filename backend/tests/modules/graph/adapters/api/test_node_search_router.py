"""POST /node/search: results, paging, warnings, errors and per-person scope."""

import uuid
from typing import TYPE_CHECKING, Any

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

ALICE = uuid.UUID(int=101)
BOB = uuid.UUID(int=102)
URL = "/api/v1/node/search"
FILM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"rating": {"type": "number", "x-menagerist": {"kind": "rating"}}},
}


class _World:
    """One app over in-memory repositories, acting as either person."""

    def __init__(self, as_user: Callable[..., None]) -> None:
        self.app = create_app()
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
    """A fresh app wired to in-memory repositories, with a film type."""
    fresh = _World(as_user)
    response = fresh.act_as(ALICE).post(
        "/api/v1/node-type",
        json={"slug": "film", "label": "Film", "attributes_schema": FILM_SCHEMA},
    )
    assert response.status_code == 201
    return fresh


def _film(client: TestClient, name: str, rating: int) -> None:
    response = client.post(
        "/api/v1/node",
        json={"name": name, "type": "film", "attributes": {"rating": rating}},
    )
    assert response.status_code == 201


def _rating(op: str, value: int) -> dict[str, Any]:
    return {"kind": "field", "type": "film", "key": "rating", "op": op, "value": value}


def _query(*children: dict[str, Any], op: str = "and", **extra: Any) -> dict[str, Any]:  # noqa: ANN401
    return {"v": 1, "where": {"op": op, "children": list(children)}, **extra}


def test_search_returns_matches_and_total(world: _World) -> None:
    """A matching filter returns only matches, with the full total."""
    client = world.act_as(ALICE)
    for i, rating in enumerate((5, 4, 2)):
        _film(client, f"Film {i}", rating)

    response = client.post(URL, json={"query": _query(_rating(">=", 4)), "limit": 10})

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["total_capped"] is False
    assert {item["name"] for item in data["items"]} == {"Film 0", "Film 1"}
    assert data["warnings"] == []
    assert data["next_cursor"] is None


def test_items_have_the_same_shape_as_the_list_route(world: _World) -> None:
    """Search items are the same NodeResponse objects that GET /node returns."""
    client = world.act_as(ALICE)
    _film(client, "Alien", 5)

    searched = client.post(URL, json={"query": _query(_rating("=", 5))}).json()

    assert searched["items"] == client.get("/api/v1/node").json()


def test_pages_through_next_cursor(world: _World) -> None:
    """The cursor from page one fetches the remaining items."""
    client = world.act_as(ALICE)
    for i in range(3):
        _film(client, f"Film {i}", 3)
    body = {"query": _query(_rating("=", 3)), "limit": 2}

    first = client.post(URL, json=body).json()
    assert len(first["items"]) == 2
    assert first["total"] == 3
    assert first["next_cursor"]

    second = client.post(URL, json={**body, "cursor": first["next_cursor"]}).json()
    assert len(second["items"]) == 1
    assert second["next_cursor"] is None
    seen = {i["id"] for i in first["items"]} | {i["id"] for i in second["items"]}
    assert len(seen) == 3


def test_tampered_cursor_is_a_400(world: _World) -> None:
    """A cursor that is not one we issued is rejected, naming the cursor."""
    client = world.act_as(ALICE)

    response = client.post(
        URL, json={"query": _query(_rating("=", 3)), "cursor": "not-a-cursor"}
    )

    assert response.status_code == 400
    assert "cursor" in response.json()["detail"]


def test_stale_field_is_a_200_with_a_warning(world: _World) -> None:
    """A condition on a removed field warns instead of failing."""
    client = world.act_as(ALICE)
    _film(client, "Alien", 5)
    stale = {"kind": "field", "type": "film", "key": "gone", "op": "=", "value": 1}

    response = client.post(URL, json={"query": _query(stale)})

    assert response.status_code == 200
    warnings = response.json()["warnings"]
    assert len(warnings) == 1
    assert warnings[0]["path"].startswith("where.children[0]")
    assert warnings[0]["message"]


def test_malformed_tree_is_a_400_naming_the_path(world: _World) -> None:
    """The problem detail carries the JSON path of the bad condition."""
    client = world.act_as(ALICE)

    response = client.post(URL, json={"query": _query({"kind": "nope"})})

    assert response.status_code == 400
    assert "where.children[0]" in response.json()["detail"]


@pytest.mark.parametrize("limit", [0, 201])
def test_limit_out_of_range_is_a_422(world: _World, limit: int) -> None:
    """The page size is bounded to 1..200."""
    client = world.act_as(ALICE)

    response = client.post(URL, json={"query": _query(), "limit": limit})

    assert response.status_code == 422


def test_unknown_body_field_is_a_422(world: _World) -> None:
    """Request bodies reject fields they do not know."""
    client = world.act_as(ALICE)

    response = client.post(URL, json={"query": _query(), "surprise": True})

    assert response.status_code == 422


def test_each_person_only_finds_their_own_items_even_through_or(
    world: _World,
) -> None:
    """An `or` group that matches both people's items still stays in scope."""
    _film(world.act_as(ALICE), "Alice film", 4)
    _film(world.act_as(BOB), "Bob film", 4)
    either = _query(_rating("=", 4), {"kind": "favourite", "value": False}, op="or")

    for person, name in ((ALICE, "Alice film"), (BOB, "Bob film")):
        client = world.act_as(person)
        for query in (_query(_rating("=", 4)), either):
            data = client.post(URL, json={"query": query}).json()
            assert [i["name"] for i in data["items"]] == [name]
            assert data["total"] == 1
