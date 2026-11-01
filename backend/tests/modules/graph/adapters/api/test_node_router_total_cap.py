"""GET /node: `Total-Count` stops at 1,000 for a text search and says so."""

import asyncio
import uuid

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
from app.modules.graph.domain.node import Node
from app.modules.graph.ports.unit_of_work import GraphRepos

DEFAULT_MEMBER_ID = uuid.UUID(int=1)
OTHER_ID = uuid.UUID(int=2)


def _client(count: int, *, others: int = 0) -> TestClient:
    app = create_app()
    repos = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )

    async def seed() -> None:
        for i in range(count):
            await repos.nodes.add(
                Node.create(owner_id=DEFAULT_MEMBER_ID, name=f"Coin {i}", type="coin")
            )

        for i in range(others):
            await repos.nodes.add(
                Node.create(owner_id=OTHER_ID, name=f"Coin {i}", type="coin")
            )

    asyncio.run(seed())
    app.dependency_overrides[get_graph_uow] = lambda: create_in_memory_graph_uow(repos)
    app.dependency_overrides[get_graph_repos] = lambda: repos
    members = InMemoryCollectionMembers()
    app.dependency_overrides[get_collection_members] = lambda: members
    return TestClient(app)


def test_search_over_the_cap_reports_a_capped_count() -> None:
    """1,005 matches: Total-Count is 1000, flagged, and paging still works."""
    client = _client(1005)

    first = client.get("/api/v1/node?q=coin&limit=10")
    after = first.json()[-1]["id"]
    second = client.get(f"/api/v1/node?q=coin&limit=10&after={after}")

    assert first.status_code == 200
    assert first.headers["Total-Count"] == "1000"
    assert first.headers["Total-Count-Capped"] == "true"
    assert len(first.json()) == 10
    assert "next" in first.headers["Link"]
    assert second.headers["Total-Count"] == "1000"
    assert second.json()[0]["id"] > after


def test_search_under_the_cap_is_exact_and_unflagged() -> None:
    """A small search keeps an exact count and no flag."""
    client = _client(7)

    response = client.get("/api/v1/node?q=coin")

    assert response.headers["Total-Count"] == "7"
    assert "Total-Count-Capped" not in response.headers


def test_list_without_search_stays_exact_above_the_cap() -> None:
    """Without `q`, 1,005 items count as 1,005."""
    client = _client(1005)

    response = client.get("/api/v1/node?limit=5")

    assert response.headers["Total-Count"] == "1005"
    assert "Total-Count-Capped" not in response.headers


def test_openapi_documents_the_count_headers() -> None:
    """The list operation describes Total-Count and its capped flag."""
    spec = _client(0).get("/api/openapi.json").json()
    headers = spec["paths"]["/api/v1/node"]["get"]["responses"]["200"]["headers"]

    assert {"Link", "Total-Count", "Total-Count-Capped"} <= set(headers)


def test_count_is_exact_above_the_cap_and_never_below_the_list() -> None:
    """1,005 matches: the count route says 1,005; the list's capped value is lower."""
    client = _client(1005, others=3)

    counted = client.get("/api/v1/node/count?q=coin")
    listed = client.get("/api/v1/node?q=coin&limit=1")

    assert counted.status_code == 200
    assert counted.json() == {"count": 1005}
    assert int(listed.headers["Total-Count"]) <= counted.json()["count"]


def test_count_follows_the_list_filters() -> None:
    """Type and favourite narrow the count as they narrow the list."""
    client = _client(4)

    assert client.get("/api/v1/node/count").json() == {"count": 4}
    assert client.get("/api/v1/node/count?type=coin").json() == {"count": 4}
    assert client.get("/api/v1/node/count?type=film").json() == {"count": 0}
    assert client.get("/api/v1/node/count?favourite=true").json() == {"count": 0}


def test_count_of_an_unknown_collection_is_the_lists_404() -> None:
    """A collection that is not there fails the same way as on the list."""
    client = _client(1)
    missing = uuid.uuid4()

    listed = client.get(f"/api/v1/node?collection={missing}")
    counted = client.get(f"/api/v1/node/count?collection={missing}")

    assert listed.status_code == counted.status_code == 404
    assert counted.json()["type"] == listed.json()["type"]


def test_count_with_a_malformed_filter_is_the_lists_422() -> None:
    """A filter that does not parse is refused identically."""
    client = _client(1)

    listed = client.get("/api/v1/node?favourite=maybe")
    counted = client.get("/api/v1/node/count?favourite=maybe")

    assert listed.status_code == counted.status_code == 422
    assert counted.json()["type"] == listed.json()["type"]


def test_count_route_is_in_the_spec() -> None:
    """The count operation is published with the shared filter parameters."""
    spec = _client(0).get("/api/openapi.json").json()
    get = spec["paths"]["/api/v1/node/count"]["get"]
    listed = spec["paths"]["/api/v1/node"]["get"]

    names = {p["name"] for p in get["parameters"]}
    assert names == {"type", "q", "favourite", "collection"}
    assert names <= {p["name"] for p in listed["parameters"]}
    assert get["operationId"] == "count_nodes"
