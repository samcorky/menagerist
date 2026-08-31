import uuid
from typing import TYPE_CHECKING

from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.modules.graph.adapters.api.dependencies import get_graph_uow
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
        edge_types=InMemoryEdgeTypeRepository(),
    )
    app.dependency_overrides[get_graph_uow] = lambda: create_in_memory_graph_uow(repos)
    return app


def _create_node(client: TestClient, *, name: str, type_: str) -> dict[str, object]:
    response = client.post("/api/v1/node", json={"name": name, "type": type_})
    result: dict[str, object] = response.json()
    return result


def _create_edge(client: TestClient) -> dict[str, object]:
    source = _create_node(client, name="Alien", type_="film")
    target = _create_node(client, name="Ridley Scott", type_="person")
    response = client.post(
        "/api/v1/edge",
        json={
            "source_id": source["id"],
            "target_id": target["id"],
            "type": "directed-by",
        },
    )
    result: dict[str, object] = response.json()
    return result


def test_create_get_list_and_404_round_trip() -> None:
    """An edge created via the API can be fetched and listed, and a miss is a 404."""
    client = TestClient(_app_with_in_memory_graph())
    source = _create_node(client, name="Alien", type_="film")
    target = _create_node(client, name="Ridley Scott", type_="person")

    create_response = client.post(
        "/api/v1/edge",
        json={
            "source_id": source["id"],
            "target_id": target["id"],
            "type": "directed-by",
        },
    )
    assert create_response.status_code == 201
    edge = create_response.json()
    assert edge["source_id"] == source["id"]
    assert edge["target_id"] == target["id"]
    assert edge["type"] == "directed-by"

    get_response = client.get(f"/api/v1/edge/{edge['id']}")
    assert get_response.status_code == 200
    assert get_response.json() == edge

    list_response = client.get("/api/v1/edge")
    assert list_response.status_code == 200
    assert edge in list_response.json()

    filtered_response = client.get(f"/api/v1/edge?node_id={target['id']}")
    assert filtered_response.status_code == 200
    assert edge in filtered_response.json()

    missing_response = client.get(f"/api/v1/edge/{uuid.uuid4()}")
    assert missing_response.status_code == 404
    assert missing_response.json()["title"] == "EdgeNotFoundError"


def test_create_edge_returns_404_when_a_node_is_missing() -> None:
    """Creating an edge to a nonexistent node returns 404."""
    client = TestClient(_app_with_in_memory_graph())
    source = _create_node(client, name="Alien", type_="film")

    response = client.post(
        "/api/v1/edge",
        json={
            "source_id": source["id"],
            "target_id": str(uuid.uuid4()),
            "type": "directed-by",
        },
    )

    assert response.status_code == 404
    assert response.json()["title"] == "NodeNotFoundError"


def test_update_edge_applies_changes() -> None:
    """PATCH updates the given fields and leaves the rest unchanged."""
    client = TestClient(_app_with_in_memory_graph())
    edge = _create_edge(client)

    update_response = client.patch(
        f"/api/v1/edge/{edge['id']}", json={"attributes": {"since": "1979"}}
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["attributes"] == {"since": "1979"}
    assert updated["type"] == "directed-by"


def test_update_edge_returns_404_when_missing() -> None:
    """PATCH on a nonexistent edge returns 404."""
    client = TestClient(_app_with_in_memory_graph())

    response = client.patch(
        f"/api/v1/edge/{uuid.uuid4()}", json={"attributes": {"since": "1979"}}
    )

    assert response.status_code == 404


def test_delete_edge_then_get_and_list_no_longer_find_it() -> None:
    """DELETE soft-deletes the edge, so subsequent GET/LIST treat it as gone."""
    client = TestClient(_app_with_in_memory_graph())
    edge = _create_edge(client)

    delete_response = client.delete(f"/api/v1/edge/{edge['id']}")
    assert delete_response.status_code == 204

    assert client.get(f"/api/v1/edge/{edge['id']}").status_code == 404
    assert edge not in client.get("/api/v1/edge").json()


def test_delete_edge_returns_404_when_missing() -> None:
    """DELETE on a nonexistent edge returns 404."""
    client = TestClient(_app_with_in_memory_graph())

    response = client.delete(f"/api/v1/edge/{uuid.uuid4()}")

    assert response.status_code == 404


def test_get_edge_response_includes_etag_and_last_modified_headers() -> None:
    """GET /api/v1/edge/{id} returns ETag and Last-Modified headers."""
    client = TestClient(_app_with_in_memory_graph())
    node_1 = _create_node(client, name="Node 1", type_="type1")
    node_2 = _create_node(client, name="Node 2", type_="type2")

    edge = client.post(
        "/api/v1/edge",
        json={"source_id": node_1["id"], "target_id": node_2["id"], "type": "test"},
    ).json()

    response = client.get(f"/api/v1/edge/{edge['id']}")

    assert response.status_code == 200
    assert "ETag" in response.headers
    assert "Last-Modified" in response.headers


def test_get_edge_returns_304_when_etag_matches() -> None:
    """GET /api/v1/edge/{id} returns 304 Not Modified when ETag matches."""
    client = TestClient(_app_with_in_memory_graph())
    node_1 = _create_node(client, name="Node 1", type_="type1")
    node_2 = _create_node(client, name="Node 2", type_="type2")
    edge = client.post(
        "/api/v1/edge",
        json={"source_id": node_1["id"], "target_id": node_2["id"], "type": "test"},
    ).json()

    initial_response = client.get(f"/api/v1/edge/{edge['id']}")
    etag = initial_response.headers["ETag"]

    response = client.get(f"/api/v1/edge/{edge['id']}", headers={"If-None-Match": etag})

    assert response.status_code == 304
    assert response.headers["ETag"] == etag


def test_get_edge_returns_304_when_not_modified_since() -> None:
    """GET /api/v1/edge/{id} returns 304 Not Modified when If-Modified-Since matches."""
    client = TestClient(_app_with_in_memory_graph())
    node_1 = _create_node(client, name="Node 1", type_="type1")
    node_2 = _create_node(client, name="Node 2", type_="type2")
    edge = client.post(
        "/api/v1/edge",
        json={"source_id": node_1["id"], "target_id": node_2["id"], "type": "test"},
    ).json()

    initial_response = client.get(f"/api/v1/edge/{edge['id']}")
    last_modified = initial_response.headers["Last-Modified"]

    response = client.get(
        f"/api/v1/edge/{edge['id']}", headers={"If-Modified-Since": last_modified}
    )

    assert response.status_code == 304
    assert response.headers["Last-Modified"] == last_modified


def test_update_edge_returns_412_when_if_match_stale() -> None:
    """PATCH /api/v1/edge/{id} returns 412 Precondition Failed.

    When If-Match is stale.
    """
    client = TestClient(_app_with_in_memory_graph())
    node_1 = _create_node(client, name="Node 1", type_="type1")
    node_2 = _create_node(client, name="Node 2", type_="type2")
    edge = client.post(
        "/api/v1/edge",
        json={"source_id": node_1["id"], "target_id": node_2["id"], "type": "test"},
    ).json()

    initial_response = client.get(f"/api/v1/edge/{edge['id']}")
    etag = initial_response.headers["ETag"]

    # Update the edge to change its ETag
    client.patch(f"/api/v1/edge/{edge['id']}", json={"type": "updated_test"})

    response = client.patch(
        f"/api/v1/edge/{edge['id']}",
        json={"type": "another_test"},
        headers={"If-Match": etag},
    )

    assert response.status_code == 412
    assert response.headers["ETag"] != etag


def test_update_edge_proceeds_when_if_match_current() -> None:
    """PATCH /api/v1/edge/{id} succeeds when If-Match matches current ETag."""
    client = TestClient(_app_with_in_memory_graph())
    node_1 = _create_node(client, name="Node 1", type_="type1")
    node_2 = _create_node(client, name="Node 2", type_="type2")
    edge = client.post(
        "/api/v1/edge",
        json={"source_id": node_1["id"], "target_id": node_2["id"], "type": "test"},
    ).json()

    initial_response = client.get(f"/api/v1/edge/{edge['id']}")
    etag = initial_response.headers["ETag"]

    response = client.patch(
        f"/api/v1/edge/{edge['id']}",
        json={"attributes": {"patched": True}},
        headers={"If-Match": etag},
    )

    assert response.status_code == 200
    updated_edge = response.json()
    assert updated_edge["attributes"] == {"patched": True}
    # type is immutable through PATCH
    assert updated_edge["type"] == "test"


def test_list_edges_link_header_present_when_more_pages_exist() -> None:
    """GET /api/v1/edge returns Link header when more pages exist."""
    client = TestClient(_app_with_in_memory_graph())
    # Create enough edges to require pagination
    for i in range(15):
        src = _create_node(client, name=f"Source {i}", type_="type")
        tgt = _create_node(client, name=f"Target {i}", type_="type")
        client.post(
            "/api/v1/edge",
            json={"source_id": src["id"], "target_id": tgt["id"], "type": "test"},
        )

    response = client.get("/api/v1/edge?limit=10")

    assert response.status_code == 200
    assert "Link" in response.headers
    assert 'rel="next"' in response.headers["Link"]


def test_list_edges_no_link_header_on_last_page() -> None:
    """GET /api/v1/edge does not return Link header on last page."""
    client = TestClient(_app_with_in_memory_graph())
    # Create fewer edges than the page size
    for i in range(5):
        src = _create_node(client, name=f"Source {i}", type_="type")
        tgt = _create_node(client, name=f"Target {i}", type_="type")
        client.post(
            "/api/v1/edge",
            json={"source_id": src["id"], "target_id": tgt["id"], "type": "test"},
        )

    response = client.get("/api/v1/edge")

    assert response.status_code == 200
    assert "Link" not in response.headers
