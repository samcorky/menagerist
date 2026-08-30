from datetime import timedelta
from email.utils import formatdate, parsedate_to_datetime
from typing import TYPE_CHECKING

from starlette.testclient import TestClient

from app.entrypoints.api import create_app
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
    """Build the app with the graph module wired to fresh in-memory.

    repositories.
    """
    app = create_app()
    repos = GraphRepos(nodes=InMemoryNodeRepository(), edges=InMemoryEdgeRepository())
    app.dependency_overrides[
        "app.modules.graph.adapters.persistence.unit_of_work.get_graph_uow"
    ] = lambda: create_in_memory_graph_uow(repos)  # type: ignore
    # Many router tests override get_graph_uow differently; replicate the same wiring
    from app.modules.graph.adapters.api.dependencies import get_graph_uow

    app.dependency_overrides[get_graph_uow] = lambda: create_in_memory_graph_uow(repos)
    return app


def _create_node(client: TestClient, *, name: str, type_: str) -> dict:
    """Create a node via the API and return the JSON response."""
    response = client.post("/api/node", json={"name": name, "type": type_})
    return response.json()


def test_last_modified_is_rfc1123_no_subsecond() -> None:
    """Test that the Last-Modified header is present and formatted correctly.

    (RFC 1123, no sub-second precision).
    """
    client = TestClient(_app_with_in_memory_graph())
    node = client.post("/api/node", json={"name": "Alien", "type": "film"}).json()

    resp = client.get(f"/api/node/{node['id']}")
    assert resp.status_code == 200
    assert "Last-Modified" in resp.headers

    # Parse the header to ensure it's valid and has no sub-second precision
    dt = parsedate_to_datetime(resp.headers["Last-Modified"])
    assert dt.microsecond == 0


def test_cache_control_present_on_get() -> None:
    """Cache-Control header must be present and set to "private, no-cache"."""
    client = TestClient(_app_with_in_memory_graph())
    node = _create_node(client, name="Alien", type_="film")

    resp = client.get(f"/api/node/{node['id']}")
    assert resp.status_code == 200
    assert "Cache-Control" in resp.headers
    assert resp.headers["Cache-Control"] == "private, no-cache"


def test_304_preserves_etag_and_last_modified() -> None:
    """304 responses should preserve ETag and Last-Modified headers."""
    client = TestClient(_app_with_in_memory_graph())
    node = _create_node(client, name="Alien", type_="film")

    initial = client.get(f"/api/node/{node['id']}")
    etag = initial.headers["ETag"]
    last_mod = initial.headers["Last-Modified"]

    r1 = client.get(f"/api/node/{node['id']}", headers={"If-None-Match": etag})
    assert r1.status_code == 304
    assert r1.headers["ETag"] == etag
    assert r1.headers["Last-Modified"] == last_mod

    r2 = client.get(f"/api/node/{node['id']}", headers={"If-Modified-Since": last_mod})
    assert r2.status_code == 304
    assert r2.headers["ETag"] == etag
    assert r2.headers["Last-Modified"] == last_mod


def test_patch_with_if_unmodified_since_returns_412_when_stale() -> None:
    """PATCH with If-Unmodified-Since returns 412 if the resource is stale."""
    client = TestClient(_app_with_in_memory_graph())
    node = _create_node(client, name="Alien", type_="film")

    initial = client.get(f"/api/node/{node['id']}")
    last_mod = initial.headers["Last-Modified"]

    # Mutate the resource
    client.patch(f"/api/node/{node['id']}", json={"name": "Alien (1980)"})

    # Use a timestamp older than the original Last-Modified to ensure the
    # precondition is considered stale regardless of sub-second timing.
    orig_dt = parsedate_to_datetime(last_mod)
    stale_dt = orig_dt - timedelta(seconds=1)
    stale_header = formatdate(stale_dt.timestamp(), usegmt=True)

    response = client.patch(
        f"/api/node/{node['id']}",
        json={"name": "Alien (1979)"},
        headers={"If-Unmodified-Since": stale_header},
    )

    assert response.status_code == 412
    assert "ETag" in response.headers


def test_etag_changes_on_mutation_and_stale_if_match_returns_412() -> None:
    """ETag should change on mutation; stale If-Match returns 412."""
    client = TestClient(_app_with_in_memory_graph())
    node = _create_node(client, name="Alien", type_="film")

    initial = client.get(f"/api/node/{node['id']}")
    etag1 = initial.headers["ETag"]

    # change the resource
    client.patch(f"/api/node/{node['id']}", json={"name": "Alien (1980)"})

    # ETag should have changed
    after = client.get(f"/api/node/{node['id']}")
    etag2 = after.headers["ETag"]
    assert etag1 != etag2

    # An attempt to PATCH with the old ETag must yield 412
    response = client.patch(
        f"/api/node/{node['id']}",
        json={"name": "Alien (1979)"},
        headers={"If-Match": etag1},
    )

    assert response.status_code == 412
    assert response.headers.get("ETag") != etag1
