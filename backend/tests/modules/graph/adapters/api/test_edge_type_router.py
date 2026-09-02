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
    """An edge type created via the API can be fetched and listed; a miss is 404."""
    client = TestClient(_app_with_in_memory_graph())

    create_response = client.post(
        "/api/v1/edge-type",
        json={
            "slug": "directed-by",
            "label": "Directed By",
            "reverse_label": "Directed",
            "directional": True,
        },
    )
    assert create_response.status_code == 201
    et = create_response.json()
    assert et["slug"] == "directed-by"
    assert et["label"] == "Directed By"
    assert et["reverse_label"] == "Directed"
    assert et["directional"] is True

    get_response = client.get(f"/api/v1/edge-type/{et['id']}")
    assert get_response.status_code == 200
    assert get_response.json() == et

    list_response = client.get("/api/v1/edge-type")
    assert list_response.status_code == 200
    assert et in list_response.json()

    missing_response = client.get(f"/api/v1/edge-type/{uuid.uuid4()}")
    assert missing_response.status_code == 404
    assert missing_response.json()["title"] == "EdgeTypeNotFoundError"


def test_create_edge_type_returns_409_on_slug_conflict() -> None:
    """POST with a duplicate slug returns 409."""
    client = TestClient(_app_with_in_memory_graph())
    client.post(
        "/api/v1/edge-type", json={"slug": "directed-by", "label": "Directed By"}
    )

    response = client.post(
        "/api/v1/edge-type", json={"slug": "directed-by", "label": "Duplicate"}
    )

    assert response.status_code == 409


def test_update_edge_type_applies_changes() -> None:
    """PATCH updates editable fields and leaves slug unchanged."""
    client = TestClient(_app_with_in_memory_graph())
    et = client.post(
        "/api/v1/edge-type", json={"slug": "directed-by", "label": "Directed By"}
    ).json()

    update_response = client.patch(
        f"/api/v1/edge-type/{et['id']}",
        json={"label": "Helmed By", "reverse_label": "Helmed"},
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["label"] == "Helmed By"
    assert updated["reverse_label"] == "Helmed"
    assert updated["slug"] == "directed-by"


def test_update_edge_type_returns_404_when_missing() -> None:
    """PATCH on a nonexistent edge type returns 404."""
    client = TestClient(_app_with_in_memory_graph())

    response = client.patch(
        f"/api/v1/edge-type/{uuid.uuid4()}", json={"label": "Ghost"}
    )

    assert response.status_code == 404


def test_delete_edge_type_then_get_returns_404() -> None:
    """DELETE soft-deletes the edge type; subsequent GET returns 404."""
    client = TestClient(_app_with_in_memory_graph())
    et = client.post(
        "/api/v1/edge-type", json={"slug": "directed-by", "label": "Directed By"}
    ).json()

    delete_response = client.delete(f"/api/v1/edge-type/{et['id']}")
    assert delete_response.status_code == 204

    assert client.get(f"/api/v1/edge-type/{et['id']}").status_code == 404
    assert et not in client.get("/api/v1/edge-type").json()


def test_delete_edge_type_returns_404_when_missing() -> None:
    """DELETE on a nonexistent edge type returns 404."""
    client = TestClient(_app_with_in_memory_graph())

    response = client.delete(f"/api/v1/edge-type/{uuid.uuid4()}")

    assert response.status_code == 404


def test_delete_edge_type_returns_409_when_edges_still_use_it() -> None:
    """DELETE returns 409 when active edges reference the edge type."""
    client = TestClient(_app_with_in_memory_graph())
    et = client.post(
        "/api/v1/edge-type", json={"slug": "directed-by", "label": "Directed By"}
    ).json()
    source = client.post("/api/v1/node", json={"name": "Ridley Scott"}).json()
    target = client.post("/api/v1/node", json={"name": "Alien"}).json()
    client.post(
        "/api/v1/edge",
        json={
            "source_id": source["id"],
            "target_id": target["id"],
            "type": "directed-by",
        },
    )

    response = client.delete(f"/api/v1/edge-type/{et['id']}")

    assert response.status_code == 409
    assert response.json()["title"] == "EdgeTypeInUseError"


def test_delete_edge_type_succeeds_when_no_active_edges_use_it() -> None:
    """DELETE succeeds when no active edges reference the edge type."""
    client = TestClient(_app_with_in_memory_graph())
    et = client.post(
        "/api/v1/edge-type", json={"slug": "directed-by", "label": "Directed By"}
    ).json()
    # A different edge type's edges should not block this deletion
    source = client.post("/api/v1/node", json={"name": "Ridley Scott"}).json()
    target = client.post("/api/v1/node", json={"name": "Alien"}).json()
    client.post(
        "/api/v1/edge",
        json={"source_id": source["id"], "target_id": target["id"], "type": "produced"},
    )

    response = client.delete(f"/api/v1/edge-type/{et['id']}")

    assert response.status_code == 204


def test_attributes_schema_round_trips_through_create_and_update() -> None:
    """attributes_schema is stored on create and can be updated via PATCH."""
    client = TestClient(_app_with_in_memory_graph())
    schema = {
        "fields": [
            {"key": "since", "label": "Since", "type": "date", "required": False}
        ]
    }

    et = client.post(
        "/api/v1/edge-type",
        json={
            "slug": "directed-by",
            "label": "Directed By",
            "attributes_schema": schema,
        },
    ).json()
    assert et["attributes_schema"] == schema

    new_schema: dict = {"fields": []}
    updated = client.patch(
        f"/api/v1/edge-type/{et['id']}",
        json={"attributes_schema": new_schema},
    ).json()
    assert updated["attributes_schema"] == new_schema
