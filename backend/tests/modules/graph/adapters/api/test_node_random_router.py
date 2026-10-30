"""GET /node/random: a random item, for one person.

Sign-in is enforced for every route by test_authenticated_routes.
"""

import uuid
from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from collections.abc import Callable

ALICE = uuid.UUID(int=101)
BOB = uuid.UUID(int=102)
URL = "/api/v1/node/random"


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
    members = InMemoryCollectionMembers()
    app.dependency_overrides[get_collection_members] = lambda: members
    as_user(app, ALICE)
    return TestClient(app)


async def test_returns_one_of_the_signed_in_persons_items(
    client: TestClient, repos: GraphRepos
) -> None:
    """Returns one of the signed in person's items, never someone else's."""
    mine = Node.create(owner_id=ALICE, name="Mine", type="film")
    await repos.nodes.add(mine)
    await repos.nodes.add(Node.create(owner_id=BOB, name="Theirs", type="film"))

    response = client.get(URL)

    assert response.status_code == 200
    assert response.json()["id"] == str(mine.id)


async def test_the_list_filters_narrow_the_pick(
    client: TestClient, repos: GraphRepos
) -> None:
    """The type filter works as it does on the list."""
    book = Node.create(owner_id=ALICE, name="Book", type="book")
    await repos.nodes.add(book)
    await repos.nodes.add(Node.create(owner_id=ALICE, name="Film", type="film"))

    response = client.get(URL, params={"type": "book"})

    assert response.json()["id"] == str(book.id)


def test_no_matching_item_is_a_404(client: TestClient) -> None:
    """No matching item is a 404, not an empty body."""
    response = client.get(URL)

    assert response.status_code == 404
    assert response.json()["detail"] == "No item matches"


def test_an_unknown_collection_is_a_404(client: TestClient) -> None:
    """A collection that does not exist is a 404."""
    response = client.get(URL, params={"collection": str(uuid.uuid7())})

    assert response.status_code == 404
