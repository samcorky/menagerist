"""POST /nodes/search/counts and GET /nodes/count/types: counts per person.

Sign-in is enforced for every route by test_authenticated_routes.
"""

import uuid
from typing import TYPE_CHECKING, Any

import pytest
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.bridges.collection_members import get_collection_members
from app.modules.graph.adapters.api.dependencies import get_graph_repos
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
from app.modules.graph.domain.node import Node
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from collections.abc import Callable

ALICE = uuid.UUID(int=101)
BOB = uuid.UUID(int=102)
COUNTS_URL = "/api/v1/nodes/search/counts"
TYPES_URL = "/api/v1/nodes/count/types"
EVERYTHING: dict[str, Any] = {"v": 1, "where": None, "sort": []}
FILMS: dict[str, Any] = {
    "v": 1,
    "where": {"op": "and", "children": [{"kind": "type", "in": ["film"]}]},
    "sort": [],
}


@pytest.fixture
def repos() -> GraphRepos:
    """Empty in-memory repositories."""
    return GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )


@pytest.fixture
def client(repos: GraphRepos, as_user: Callable[..., None]) -> TestClient:
    """A client acting as Alice over those repositories."""
    app = create_app()
    app.dependency_overrides[get_graph_repos] = lambda: repos
    as_user(app, ALICE)
    return TestClient(app)


async def _seed(repos: GraphRepos) -> None:
    for owner, slug in (
        (ALICE, "film"),
        (ALICE, "film"),
        (ALICE, None),
        (BOB, "film"),
        (BOB, "book"),
    ):
        await repos.nodes.add(Node.create(owner_id=owner, name="n", type=slug))


async def test_counts_each_named_query_for_the_signed_in_person(
    client: TestClient, repos: GraphRepos
) -> None:
    """Counts each named query for the signed in person."""
    await _seed(repos)

    response = client.post(
        COUNTS_URL, json={"queries": {"all": EVERYTHING, "films": FILMS}}
    )

    assert response.status_code == 200
    assert response.json() == {
        "counts": {
            "all": {"total": 3, "total_capped": False, "warnings": []},
            "films": {"total": 2, "total_capped": False, "warnings": []},
        }
    }


def test_a_malformed_query_is_a_400_that_names_the_query(client: TestClient) -> None:
    """A malformed query is a 400 that names the query."""
    response = client.post(
        COUNTS_URL, json={"queries": {"bad": {"v": 1, "where": {"op": "xor"}}}}
    )

    assert response.status_code == 400
    assert response.json()["detail"].startswith("queries.bad: ")


def test_an_empty_batch_is_a_400(client: TestClient) -> None:
    """An empty batch is a 400."""
    response = client.post(COUNTS_URL, json={"queries": {}})

    assert response.status_code == 400
    assert response.json()["detail"].startswith("queries: ")


def test_a_body_without_queries_is_a_422(client: TestClient) -> None:
    """A body without queries is a 422."""
    assert client.post(COUNTS_URL, json={}).status_code == 422


async def test_counts_items_per_type_in_use_for_the_signed_in_person(
    client: TestClient, repos: GraphRepos
) -> None:
    """Counts items per type in use for the signed in person."""
    await _seed(repos)

    response = client.get(TYPES_URL)

    assert response.status_code == 200
    assert response.json() == [
        {"type": "film", "count": 2},
        {"type": None, "count": 1},
    ]


def test_counts_nothing_with_no_items(client: TestClient) -> None:
    """Counts nothing with no items."""
    response = client.get(TYPES_URL)

    assert response.status_code == 200
    assert response.json() == []


async def test_counts_only_the_types_on_a_collection(
    repos: GraphRepos, as_user: Callable[..., None]
) -> None:
    """?collection= counts the types of that collection's items alone."""
    await _seed(repos)
    mine = await repos.nodes.list(scope=ContentFilter.of(ALICE), after=None, limit=10)
    on_shelf = [n.id for n in mine if n.type is None]
    members = InMemoryCollectionMembers()
    collection = uuid.uuid4()
    members.add_collection(collection, on_shelf, owner_id=ALICE)
    app = create_app()
    app.dependency_overrides[get_graph_repos] = lambda: repos
    app.dependency_overrides[get_collection_members] = lambda: members
    as_user(app, ALICE)

    response = TestClient(app).get(TYPES_URL, params={"collection": str(collection)})

    assert response.status_code == 200
    assert response.json() == [{"type": None, "count": 1}]


def test_an_unknown_collection_is_not_found(
    repos: GraphRepos, as_user: Callable[..., None]
) -> None:
    """A collection that does not exist answers 404."""
    app = create_app()
    app.dependency_overrides[get_graph_repos] = lambda: repos
    app.dependency_overrides[get_collection_members] = InMemoryCollectionMembers
    as_user(app, ALICE)

    response = TestClient(app).get(TYPES_URL, params={"collection": str(uuid.uuid4())})

    assert response.status_code == 404
