import uuid
from typing import TYPE_CHECKING

from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.modules.graph.adapters.api.dependencies import get_graph_uow
from app.modules.graph.adapters.persistence.in_memory_edge_repository import (
    InMemoryEdgeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.adapters.persistence.unit_of_work import (
    create_in_memory_graph_uow,
)
from app.modules.graph.ports.unit_of_work import GraphRepos

if TYPE_CHECKING:
    from fastapi import FastAPI


def _app_with_in_memory_graph() -> FastAPI:
    """Build the app with the graph module wired to fresh in-memory repositories.

    Router tests exercise the API layer, not real persistence - the in-memory
    adapter is the fast, Docker-free double `backend/README.md` prescribes for
    this test tier.
    """
    app = create_app()
    repos = GraphRepos(nodes=InMemoryNodeRepository(), edges=InMemoryEdgeRepository())
    app.dependency_overrides[get_graph_uow] = lambda: create_in_memory_graph_uow(repos)
    return app


def test_create_get_list_and_404_round_trip() -> None:
    """A node created via the API can be fetched and listed, and a miss is a 404."""
    client = TestClient(_app_with_in_memory_graph())

    create_response = client.post(
        "/api/node",
        json={"name": "Alien", "type": "film", "attributes": {"title": "Alien"}},
    )
    assert create_response.status_code == 201
    node = create_response.json()
    assert node["type"] == "film"
    assert node["attributes"] == {"title": "Alien"}

    get_response = client.get(f"/api/node/{node['id']}")
    assert get_response.status_code == 200
    assert get_response.json() == node

    list_response = client.get("/api/node")
    assert list_response.status_code == 200
    assert node in list_response.json()

    missing_response = client.get(f"/api/node/{uuid.uuid4()}")
    assert missing_response.status_code == 404
    assert missing_response.json()["title"] == "NodeNotFoundError"


def test_update_node_applies_changes() -> None:
    """PATCH updates the given fields and leaves the rest unchanged."""
    client = TestClient(_app_with_in_memory_graph())
    node = client.post("/api/node", json={"name": "Alien", "type": "film"}).json()

    update_response = client.patch(
        f"/api/node/{node['id']}", json={"name": "Alien (1979)"}
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["name"] == "Alien (1979)"
    assert updated["type"] == "film"


def test_update_node_returns_404_when_missing() -> None:
    """PATCH on a nonexistent node returns 404."""
    client = TestClient(_app_with_in_memory_graph())

    response = client.patch(f"/api/node/{uuid.uuid4()}", json={"name": "Alien"})

    assert response.status_code == 404


def test_delete_node_then_get_and_list_no_longer_find_it() -> None:
    """DELETE soft-deletes the node, so subsequent GET/LIST treat it as gone."""
    client = TestClient(_app_with_in_memory_graph())
    node = client.post("/api/node", json={"name": "Alien", "type": "film"}).json()

    delete_response = client.delete(f"/api/node/{node['id']}")
    assert delete_response.status_code == 204

    assert client.get(f"/api/node/{node['id']}").status_code == 404
    assert node not in client.get("/api/node").json()


def test_delete_node_returns_404_when_missing() -> None:
    """DELETE on a nonexistent node returns 404."""
    client = TestClient(_app_with_in_memory_graph())

    response = client.delete(f"/api/node/{uuid.uuid4()}")

    assert response.status_code == 404
