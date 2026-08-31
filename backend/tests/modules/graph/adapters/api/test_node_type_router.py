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
    app = create_app()
    repos = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )
    app.dependency_overrides[get_graph_uow] = lambda: create_in_memory_graph_uow(repos)
    return app


def test_create_get_list_and_404_round_trip() -> None:
    """A node type created via the API can be fetched and listed; a miss is 404."""
    client = TestClient(_app_with_in_memory_graph())

    create_response = client.post(
        "/api/v1/node-type",
        json={"slug": "film", "label": "Film", "description": "Motion pictures"},
    )
    assert create_response.status_code == 201
    nt = create_response.json()
    assert nt["slug"] == "film"
    assert nt["label"] == "Film"
    assert nt["description"] == "Motion pictures"

    get_response = client.get(f"/api/v1/node-type/{nt['id']}")
    assert get_response.status_code == 200
    assert get_response.json() == nt

    list_response = client.get("/api/v1/node-type")
    assert list_response.status_code == 200
    assert nt in list_response.json()

    missing_response = client.get(f"/api/v1/node-type/{uuid.uuid4()}")
    assert missing_response.status_code == 404
    assert missing_response.json()["title"] == "NodeTypeNotFoundError"


def test_create_node_type_returns_409_on_slug_conflict() -> None:
    """POST with a duplicate slug returns 409."""
    client = TestClient(_app_with_in_memory_graph())
    client.post("/api/v1/node-type", json={"slug": "film", "label": "Film"})

    response = client.post(
        "/api/v1/node-type", json={"slug": "film", "label": "Duplicate"}
    )

    assert response.status_code == 409


def test_update_node_type_applies_changes() -> None:
    """PATCH updates the label and leaves slug unchanged."""
    client = TestClient(_app_with_in_memory_graph())
    nt = client.post("/api/v1/node-type", json={"slug": "film", "label": "Film"}).json()

    update_response = client.patch(
        f"/api/v1/node-type/{nt['id']}", json={"label": "Movie"}
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["label"] == "Movie"
    assert updated["slug"] == "film"


def test_update_node_type_returns_404_when_missing() -> None:
    """PATCH on a nonexistent node type returns 404."""
    client = TestClient(_app_with_in_memory_graph())

    response = client.patch(
        f"/api/v1/node-type/{uuid.uuid4()}", json={"label": "Ghost"}
    )

    assert response.status_code == 404


def test_delete_node_type_then_get_returns_404() -> None:
    """DELETE soft-deletes the node type; subsequent GET returns 404."""
    client = TestClient(_app_with_in_memory_graph())
    nt = client.post("/api/v1/node-type", json={"slug": "film", "label": "Film"}).json()

    delete_response = client.delete(f"/api/v1/node-type/{nt['id']}")
    assert delete_response.status_code == 204

    assert client.get(f"/api/v1/node-type/{nt['id']}").status_code == 404
    assert nt not in client.get("/api/v1/node-type").json()


def test_delete_node_type_returns_404_when_missing() -> None:
    """DELETE on a nonexistent node type returns 404."""
    client = TestClient(_app_with_in_memory_graph())

    response = client.delete(f"/api/v1/node-type/{uuid.uuid4()}")

    assert response.status_code == 404


def test_attributes_schema_round_trips_through_create_and_update() -> None:
    """attributes_schema is stored on create and can be updated via PATCH."""
    client = TestClient(_app_with_in_memory_graph())
    schema = {
        "fields": [
            {"key": "year", "label": "Year", "type": "number", "required": False}
        ]
    }

    nt = client.post(
        "/api/v1/node-type",
        json={"slug": "film", "label": "Film", "attributes_schema": schema},
    ).json()
    assert nt["attributes_schema"] == schema

    new_schema: dict = {"fields": []}
    updated = client.patch(
        f"/api/v1/node-type/{nt['id']}",
        json={"attributes_schema": new_schema},
    ).json()
    assert updated["attributes_schema"] == new_schema
