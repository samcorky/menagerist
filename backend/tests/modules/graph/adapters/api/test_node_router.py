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
from app.modules.graph.adapters.persistence.in_memory_node_type_repository import (
    InMemoryNodeTypeRepository,
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
    repos = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
    )
    app.dependency_overrides[get_graph_uow] = lambda: create_in_memory_graph_uow(repos)
    return app


def test_create_get_list_and_404_round_trip() -> None:
    """A node created via the API can be fetched and listed, and a miss is a 404."""
    client = TestClient(_app_with_in_memory_graph())

    create_response = client.post(
        "/api/v1/node",
        json={"name": "Alien", "type": "film", "attributes": {"title": "Alien"}},
    )
    assert create_response.status_code == 201
    node = create_response.json()
    assert node["type"] == "film"
    assert node["attributes"] == {"title": "Alien"}

    get_response = client.get(f"/api/v1/node/{node['id']}")
    assert get_response.status_code == 200
    assert get_response.json() == node

    list_response = client.get("/api/v1/node")
    assert list_response.status_code == 200
    assert node in list_response.json()

    missing_response = client.get(f"/api/v1/node/{uuid.uuid4()}")
    assert missing_response.status_code == 404
    assert missing_response.json()["title"] == "NodeNotFoundError"


def test_update_node_applies_changes() -> None:
    """PATCH updates the given fields and leaves the rest unchanged."""
    client = TestClient(_app_with_in_memory_graph())
    node = client.post("/api/v1/node", json={"name": "Alien", "type": "film"}).json()

    update_response = client.patch(
        f"/api/v1/node/{node['id']}", json={"name": "Alien (1979)"}
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["name"] == "Alien (1979)"
    assert updated["type"] == "film"


def test_update_node_returns_404_when_missing() -> None:
    """PATCH on a nonexistent node returns 404."""
    client = TestClient(_app_with_in_memory_graph())

    response = client.patch(f"/api/v1/node/{uuid.uuid4()}", json={"name": "Alien"})

    assert response.status_code == 404


def test_delete_node_then_get_and_list_no_longer_find_it() -> None:
    """DELETE soft-deletes the node, so subsequent GET/LIST treat it as gone."""
    client = TestClient(_app_with_in_memory_graph())
    node = client.post("/api/v1/node", json={"name": "Alien", "type": "film"}).json()

    delete_response = client.delete(f"/api/v1/node/{node['id']}")
    assert delete_response.status_code == 204

    assert client.get(f"/api/v1/node/{node['id']}").status_code == 404
    assert node not in client.get("/api/v1/node").json()


def test_delete_node_returns_404_when_missing() -> None:
    """DELETE on a nonexistent node returns 404."""
    client = TestClient(_app_with_in_memory_graph())

    response = client.delete(f"/api/v1/node/{uuid.uuid4()}")

    assert response.status_code == 404


def test_list_nodes_filters_by_type() -> None:
    """GET /api/v1/node?type=film returns only film nodes."""
    client = TestClient(_app_with_in_memory_graph())
    film = client.post("/api/v1/node", json={"name": "Alien", "type": "film"}).json()
    client.post("/api/v1/node", json={"name": "Ridley Scott", "type": "person"})

    response = client.get("/api/v1/node?type=film")

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["id"] == film["id"]


def test_list_nodes_search_by_name() -> None:
    """GET /api/v1/node?q=alien returns only nodes whose name contains the query."""
    client = TestClient(_app_with_in_memory_graph())
    client.post("/api/v1/node", json={"name": "Alien", "type": "film"})
    client.post("/api/v1/node", json={"name": "Predator", "type": "film"})

    response = client.get("/api/v1/node?q=alien")

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["name"] == "Alien"


def test_list_nodes_search_and_type_filter_combine() -> None:
    """GET /api/v1/node?q=alien&type=film applies both filters."""
    client = TestClient(_app_with_in_memory_graph())
    client.post("/api/v1/node", json={"name": "Alien", "type": "film"})
    client.post("/api/v1/node", json={"name": "Alien character", "type": "person"})

    response = client.get("/api/v1/node?q=alien&type=film")

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["type"] == "film"


def test_get_node_response_includes_etag_and_last_modified_headers() -> None:
    """GET /api/v1/node/{id} returns ETag and Last-Modified headers."""
    client = TestClient(_app_with_in_memory_graph())
    node = client.post("/api/v1/node", json={"name": "Alien", "type": "film"}).json()

    response = client.get(f"/api/v1/node/{node['id']}")

    assert response.status_code == 200
    assert "ETag" in response.headers
    assert "Last-Modified" in response.headers


def test_get_node_returns_304_when_etag_matches() -> None:
    """GET /api/v1/node/{id} returns 304 Not Modified when ETag matches."""
    client = TestClient(_app_with_in_memory_graph())
    node = client.post("/api/v1/node", json={"name": "Alien", "type": "film"}).json()

    initial_response = client.get(f"/api/v1/node/{node['id']}")
    etag = initial_response.headers["ETag"]

    response = client.get(f"/api/v1/node/{node['id']}", headers={"If-None-Match": etag})

    assert response.status_code == 304
    assert response.headers["ETag"] == etag


def test_get_node_returns_304_when_not_modified_since() -> None:
    """GET /api/v1/node/{id} returns 304 Not Modified when If-Modified-Since matches."""
    client = TestClient(_app_with_in_memory_graph())
    node = client.post("/api/v1/node", json={"name": "Alien", "type": "film"}).json()

    initial_response = client.get(f"/api/v1/node/{node['id']}")
    last_modified = initial_response.headers["Last-Modified"]

    response = client.get(
        f"/api/v1/node/{node['id']}", headers={"If-Modified-Since": last_modified}
    )

    assert response.status_code == 304
    assert response.headers["Last-Modified"] == last_modified


def test_update_node_returns_412_when_if_match_stale() -> None:
    """PATCH /api/v1/node/{id} returns 412 Precondition Failed.

    When If-Match is stale.
    """
    client = TestClient(_app_with_in_memory_graph())
    node = client.post("/api/v1/node", json={"name": "Alien", "type": "film"}).json()

    initial_response = client.get(f"/api/v1/node/{node['id']}")
    etag = initial_response.headers["ETag"]

    # Update the node to change its ETag
    client.patch(f"/api/v1/node/{node['id']}", json={"name": "Alien (1979)"})

    response = client.patch(
        f"/api/v1/node/{node['id']}",
        json={"name": "Alien (1980)"},
        headers={"If-Match": etag},
    )

    assert response.status_code == 412
    assert response.headers["ETag"] != etag


def test_update_node_proceeds_when_if_match_current() -> None:
    """PATCH /api/v1/node/{id} succeeds when If-Match matches current ETag."""
    client = TestClient(_app_with_in_memory_graph())
    node = client.post("/api/v1/node", json={"name": "Alien", "type": "film"}).json()

    initial_response = client.get(f"/api/v1/node/{node['id']}")
    etag = initial_response.headers["ETag"]

    response = client.patch(
        f"/api/v1/node/{node['id']}",
        json={"name": "Alien (1979)"},
        headers={"If-Match": etag},
    )

    assert response.status_code == 200
    updated_node = response.json()
    assert updated_node["name"] == "Alien (1979)"


def test_list_nodes_link_header_present_when_more_pages_exist() -> None:
    """GET /api/v1/node returns Link header when more pages exist."""
    client = TestClient(_app_with_in_memory_graph())
    # Create enough nodes to require pagination
    for i in range(15):
        client.post("/api/v1/node", json={"name": f"Node {i}", "type": "test"})

    response = client.get("/api/v1/node?limit=10")

    assert response.status_code == 200
    assert "Link" in response.headers
    assert 'rel="next"' in response.headers["Link"]


def test_list_nodes_no_link_header_on_last_page() -> None:
    """GET /api/v1/node does not return Link header on last page."""
    client = TestClient(_app_with_in_memory_graph())
    # Create fewer nodes than the page size (assuming default page size is 10)
    for i in range(5):
        client.post("/api/v1/node", json={"name": f"Node {i}", "type": "test"})

    response = client.get("/api/v1/node")

    assert response.status_code == 200
    assert "Link" not in response.headers
