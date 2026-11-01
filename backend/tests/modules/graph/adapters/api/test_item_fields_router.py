"""GET /node/item-fields: the per-item fields in use, per person.

Sign-in is enforced for every route by test_authenticated_routes.
"""

import uuid
from typing import TYPE_CHECKING

import pytest
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.modules.graph.adapters.api.dependencies import get_graph_repos
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

if TYPE_CHECKING:
    from collections.abc import Callable

ALICE = uuid.UUID(int=101)
BOB = uuid.UUID(int=102)
URL = "/api/v1/node/item-fields"
SCHEMA = {
    "type": "object",
    "properties": {
        "signed": {
            "type": "boolean",
            "title": "Signed copy",
            "x-menagerist": {"kind": "boolean"},
        }
    },
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


async def test_lists_fields_as_key_kind_label_count(
    client: TestClient, repos: GraphRepos
) -> None:
    """Lists fields as key kind label count."""
    await repos.nodes.add(Node.create(owner_id=ALICE, name="A", extra_schema=SCHEMA))
    await repos.nodes.add(Node.create(owner_id=BOB, name="B", extra_schema=SCHEMA))

    response = client.get(URL)

    assert response.status_code == 200
    assert response.json() == [
        {"key": "signed", "kind": "boolean", "label": "Signed copy", "count": 1}
    ]


def test_returns_an_empty_list_with_no_overlays(client: TestClient) -> None:
    """Returns an empty list with no overlays."""
    response = client.get(URL)

    assert response.status_code == 200
    assert response.json() == []
