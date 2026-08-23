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
