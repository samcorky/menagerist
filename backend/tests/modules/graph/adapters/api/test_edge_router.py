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


def _create_node(client: TestClient, *, name: str, type_: str) -> dict[str, object]:
    response = client.post("/api/nodes", json={"name": name, "type": type_})
    result: dict[str, object] = response.json()
    return result


def _create_edge(client: TestClient) -> dict[str, object]:
    source = _create_node(client, name="Alien", type_="film")
    target = _create_node(client, name="Ridley Scott", type_="person")
    response = client.post(
        "/api/edges",
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
        "/api/edges",
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

    get_response = client.get(f"/api/edges/{edge['id']}")
    assert get_response.status_code == 200
    assert get_response.json() == edge

    list_response = client.get("/api/edges")
    assert list_response.status_code == 200
    assert edge in list_response.json()["items"]

    filtered_response = client.get(f"/api/edges?node_id={target['id']}")
    assert filtered_response.status_code == 200
    assert edge in filtered_response.json()["items"]

    missing_response = client.get(f"/api/edges/{uuid.uuid4()}")
    assert missing_response.status_code == 404
    assert missing_response.json()["title"] == "EdgeNotFoundError"


def test_create_edge_returns_404_when_a_node_is_missing() -> None:
    """Creating an edge to a nonexistent node returns 404."""
    client = TestClient(_app_with_in_memory_graph())
    source = _create_node(client, name="Alien", type_="film")

    response = client.post(
        "/api/edges",
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
        f"/api/edges/{edge['id']}", json={"attributes": {"since": "1979"}}
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["attributes"] == {"since": "1979"}
    assert updated["type"] == "directed-by"


def test_update_edge_returns_404_when_missing() -> None:
    """PATCH on a nonexistent edge returns 404."""
    client = TestClient(_app_with_in_memory_graph())

    response = client.patch(
        f"/api/edges/{uuid.uuid4()}", json={"attributes": {"since": "1979"}}
    )

    assert response.status_code == 404


def test_delete_edge_then_get_and_list_no_longer_find_it() -> None:
    """DELETE soft-deletes the edge, so subsequent GET/LIST treat it as gone."""
    client = TestClient(_app_with_in_memory_graph())
    edge = _create_edge(client)

    delete_response = client.delete(f"/api/edges/{edge['id']}")
    assert delete_response.status_code == 204

    assert client.get(f"/api/edges/{edge['id']}").status_code == 404
    assert edge not in client.get("/api/edges").json()["items"]


def test_delete_edge_returns_404_when_missing() -> None:
    """DELETE on a nonexistent edge returns 404."""
    client = TestClient(_app_with_in_memory_graph())

    response = client.delete(f"/api/edges/{uuid.uuid4()}")

    assert response.status_code == 404
