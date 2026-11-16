"""The contents and path routes, including with two signed-in people."""

import uuid
from typing import TYPE_CHECKING

import pytest
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.bridges.collection_members import get_collection_members
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

    from app.modules.graph.domain.edge import Edge

ALICE = uuid.UUID(int=101)
BOB = uuid.UUID(int=102)


class _World:
    """One app, with helpers to act as either person."""

    def __init__(self, as_user: Callable[..., None]) -> None:
        self.app: FastAPI = create_app()
        edges: dict[uuid.UUID, Edge] = {}
        repos = GraphRepos(
            nodes=InMemoryNodeRepository(edges=edges),
            edges=InMemoryEdgeRepository(edges),
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


def _item(client: TestClient, name: str) -> str:
    response = client.post("/api/v1/nodes", json={"name": name})
    assert response.status_code == 201
    return str(response.json()["id"])


def _hold(client: TestClient, outer: str, inner: str, slug: str = "contains") -> None:
    response = client.post(
        "/api/v1/edges", json={"source_id": outer, "target_id": inner, "type": slug}
    )
    assert response.status_code == 201


def _relationship(client: TestClient, slug: str, *, directional: bool = True) -> None:
    """A relationship whose source holds its target, or one with no direction."""
    response = client.post(
        "/api/v1/edge-types",
        json={
            "slug": slug,
            "label": slug,
            "directional": directional,
            "holder": "source" if directional else "none",
        },
    )
    assert response.status_code == 201


def _shed_box_bag(client: TestClient) -> tuple[str, str, str]:
    _relationship(client, "contains")
    shed, box, bag = (_item(client, n) for n in ("shed", "box", "bag"))
    _hold(client, shed, box)
    _hold(client, box, bag)
    return shed, box, bag


def test_contents_lists_nested_items_with_their_depth(world: _World) -> None:
    """The shed holds the box and, through it, the bag."""
    client = world.act_as(ALICE)
    shed, box, bag = _shed_box_bag(client)

    response = client.get(
        f"/api/v1/nodes/{shed}/contents",
        params={"relationship": "contains", "depth": 3},
    )

    assert response.status_code == 200
    assert [(e["item"]["id"], e["depth"]) for e in response.json()] == [
        (box, 1),
        (bag, 2),
    ]


def test_contents_pages_with_a_link_header(world: _World) -> None:
    """A full page names the id to continue after."""
    client = world.act_as(ALICE)
    shed, box, bag = _shed_box_bag(client)
    url = f"/api/v1/nodes/{shed}/contents"

    first = client.get(url, params={"relationship": "contains", "depth": 3, "limit": 1})
    second = client.get(
        url,
        params={"relationship": "contains", "depth": 3, "limit": 1, "after": box},
    )

    assert [e["item"]["id"] for e in first.json()] == [box]
    assert box in first.headers["Link"]
    assert [e["item"]["id"] for e in second.json()] == [bag]
    assert "Link" not in second.headers


def test_path_lists_holders_outermost_first(world: _World) -> None:
    """The bag is in the box in the shed."""
    client = world.act_as(ALICE)
    shed, box, bag = _shed_box_bag(client)

    response = client.get(
        f"/api/v1/nodes/{bag}/path", params={"relationship": "contains"}
    )

    assert response.status_code == 200
    assert [n["id"] for n in response.json()] == [shed, box]


def test_a_missing_item_is_404_and_a_bad_request_is_400(world: _World) -> None:
    """Unknown item, unknown relationship and no-direction relationship."""
    client = world.act_as(ALICE)
    _relationship(client, "contains")
    _relationship(client, "sibling", directional=False)
    item = _item(client, "box")
    base = f"/api/v1/nodes/{item}"

    missing = client.get(
        f"/api/v1/nodes/{uuid.uuid4()}/contents", params={"relationship": "contains"}
    )
    unknown = client.get(f"{base}/path", params={"relationship": "nope"})
    flat = client.get(f"{base}/path", params={"relationship": "sibling"})
    deep = client.get(
        f"{base}/contents", params={"relationship": "contains", "depth": 26}
    )
    absent = client.get(f"{base}/contents")

    assert missing.status_code == 404
    assert unknown.status_code == 404
    assert flat.status_code == 400
    assert deep.status_code == 400
    assert absent.status_code == 422


def test_another_persons_item_has_no_contents_or_path(world: _World) -> None:
    """Bob cannot read Alice's shed, or walk her connections from his own item."""
    alice = world.act_as(ALICE)
    shed, box, _ = _shed_box_bag(alice)

    bob = world.act_as(BOB)
    contents = bob.get(
        f"/api/v1/nodes/{shed}/contents", params={"relationship": "contains"}
    )
    path = bob.get(f"/api/v1/nodes/{box}/path", params={"relationship": "contains"})

    assert contents.status_code == 404
    assert path.status_code == 404
