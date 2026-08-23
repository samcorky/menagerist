import uuid

from starlette.testclient import TestClient

from app.entrypoints.api import create_app


def test_create_get_list_and_404_round_trip() -> None:
    """A node created via the API can be fetched and listed, and a miss is a 404."""
    client = TestClient(create_app())

    create_response = client.post(
        "/api/nodes",
        json={"name": "Alien", "type": "film", "attributes": {"title": "Alien"}},
    )
    assert create_response.status_code == 201
    node = create_response.json()
    assert node["type"] == "film"
    assert node["attributes"] == {"title": "Alien"}

    get_response = client.get(f"/api/nodes/{node['id']}")
    assert get_response.status_code == 200
    assert get_response.json() == node

    list_response = client.get("/api/nodes")
    assert list_response.status_code == 200
    assert node in list_response.json()["items"]

    missing_response = client.get(f"/api/nodes/{uuid.uuid4()}")
    assert missing_response.status_code == 404
    assert missing_response.json()["title"] == "NodeNotFoundError"


def test_update_node_applies_changes() -> None:
    """PATCH updates the given fields and leaves the rest unchanged."""
    client = TestClient(create_app())
    node = client.post("/api/nodes", json={"name": "Alien", "type": "film"}).json()

    update_response = client.patch(
        f"/api/nodes/{node['id']}", json={"name": "Alien (1979)"}
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["name"] == "Alien (1979)"
    assert updated["type"] == "film"


def test_update_node_returns_404_when_missing() -> None:
    """PATCH on a nonexistent node returns 404."""
    client = TestClient(create_app())

    response = client.patch(f"/api/nodes/{uuid.uuid4()}", json={"name": "Alien"})

    assert response.status_code == 404


def test_delete_node_then_get_and_list_no_longer_find_it() -> None:
    """DELETE soft-deletes the node, so subsequent GET/LIST treat it as gone."""
    client = TestClient(create_app())
    node = client.post("/api/nodes", json={"name": "Alien", "type": "film"}).json()

    delete_response = client.delete(f"/api/nodes/{node['id']}")
    assert delete_response.status_code == 204

    assert client.get(f"/api/nodes/{node['id']}").status_code == 404
    assert node not in client.get("/api/nodes").json()["items"]


def test_delete_node_returns_404_when_missing() -> None:
    """DELETE on a nonexistent node returns 404."""
    client = TestClient(create_app())

    response = client.delete(f"/api/nodes/{uuid.uuid4()}")

    assert response.status_code == 404
