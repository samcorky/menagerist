"""Lists and searches say where each item's cover thumbnail is."""

import uuid

from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.bridges.item_covers import get_item_covers
from app.modules.graph.adapters.api.dependencies import get_graph_repos, get_graph_uow
from app.modules.graph.adapters.persistence.in_memory_edge_repository import (
    InMemoryEdgeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_edge_type_repository import (
    InMemoryEdgeTypeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_item_covers import (
    InMemoryItemCovers,
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

_THUMBNAIL = "/api/v1/media/abc/thumbnail"


def _client() -> tuple[TestClient, InMemoryItemCovers]:
    app = create_app()
    repos = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )
    covers = InMemoryItemCovers()
    app.dependency_overrides[get_graph_uow] = lambda: create_in_memory_graph_uow(repos)
    app.dependency_overrides[get_graph_repos] = lambda: repos
    app.dependency_overrides[get_item_covers] = lambda: covers
    return TestClient(app), covers


def _make_two(client: TestClient) -> tuple[str, str]:
    with_cover = client.post("/api/v1/nodes", json={"name": "Alien"}).json()["id"]
    bare = client.post("/api/v1/nodes", json={"name": "Aliens"}).json()["id"]
    return with_cover, bare


def test_the_list_gives_each_item_its_cover_thumbnail() -> None:
    """An item with a cover carries its thumbnail; one without has null."""
    client, covers = _client()
    with_cover, bare = _make_two(client)
    covers.set(uuid.UUID(with_cover), _THUMBNAIL)

    listed = {n["id"]: n for n in client.get("/api/v1/nodes").json()}

    assert listed[with_cover]["cover_thumbnail_url"] == _THUMBNAIL
    assert listed[bare]["cover_thumbnail_url"] is None


def test_a_search_gives_each_item_its_cover_thumbnail() -> None:
    """Search pages carry covers the same way."""
    client, covers = _client()
    with_cover, bare = _make_two(client)
    covers.set(uuid.UUID(with_cover), _THUMBNAIL)

    response = client.post(
        "/api/v1/nodes/search", json={"query": {"v": 1, "where": None}}
    )

    found = {n["id"]: n for n in response.json()["items"]}
    assert found[with_cover]["cover_thumbnail_url"] == _THUMBNAIL
    assert found[bare]["cover_thumbnail_url"] is None


def test_fetching_one_item_does_not_look_up_its_cover() -> None:
    """Only lists and searches fill the field; a single read leaves it null."""
    client, covers = _client()
    with_cover, _ = _make_two(client)
    covers.set(uuid.UUID(with_cover), _THUMBNAIL)

    assert (
        client.get(f"/api/v1/nodes/{with_cover}").json()["cover_thumbnail_url"] is None
    )
    assert covers.asked == []


def test_a_random_pick_gives_its_cover_thumbnail() -> None:
    """The surprise-me pick carries its cover too, so its page can open with it."""
    client, covers = _client()
    with_cover = client.post("/api/v1/nodes", json={"name": "Alien"}).json()["id"]
    covers.set(uuid.UUID(with_cover), _THUMBNAIL)

    picked = client.get("/api/v1/nodes/random").json()

    assert picked["id"] == with_cover
    assert picked["cover_thumbnail_url"] == _THUMBNAIL
