"""Sorting and paging of the connections list."""

from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlparse

import pytest
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.modules.graph.adapters.api.dependencies import get_graph_repos, get_graph_uow
from app.modules.graph.adapters.api.edge.schemas import EdgeResponse
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
from app.modules.graph.application.list_edges import EdgeSort
from app.modules.graph.ports.unit_of_work import GraphRepos

if TYPE_CHECKING:
    from fastapi import FastAPI

BASE = "/api/v1/edges"
TYPES = ["owns", "Likes", "owns", "directed-by", "Likes", "a-b", "owns"]


def _app() -> FastAPI:
    app = create_app()
    repos = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )
    app.dependency_overrides[get_graph_uow] = lambda: create_in_memory_graph_uow(repos)
    app.dependency_overrides[get_graph_repos] = lambda: repos
    return app


def _node(client: TestClient, name: str) -> str:
    response = client.post("/api/v1/nodes", json={"name": name, "type": "thing"})
    assert response.status_code == 201
    return str(response.json()["id"])


def _edges(client: TestClient, hub: str | None = None) -> list[dict[str, Any]]:
    """Create one connection per entry of `TYPES`, all touching `hub` if given."""
    created = []
    for n, type_ in enumerate(TYPES):
        source = hub or _node(client, f"s{n}")
        response = client.post(
            BASE,
            json={
                "source_id": source,
                "target_id": _node(client, f"t{n}"),
                "type": type_,
            },
        )
        assert response.status_code == 201
        created.append(response.json())
    return created


def _next_after(link: str) -> str:
    """The `after` cursor a `Link` header value points to."""
    url = link[link.index("<") + 1 : link.index(">")]
    return parse_qs(urlparse(url).query)["after"][0]


def _walk(client: TestClient, params: dict[str, Any]) -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []
    while True:
        response = client.get(BASE, params=params)
        assert response.status_code == 200
        seen.extend(response.json())
        if "Link" not in response.headers:
            return seen
        params = {**params, "after": _next_after(response.headers["Link"])}


@pytest.mark.parametrize("order", ["asc", "desc"])
@pytest.mark.parametrize("sort", [key.value for key in EdgeSort])
@pytest.mark.parametrize("filtered", [False, True])
def test_edges_walk_every_sort_key_to_the_end(
    sort: str, order: str, filtered: bool
) -> None:
    """Following `Link` visits each connection once, whole or for one item."""
    client = TestClient(_app())
    hub = _node(client, "hub") if filtered else None
    created = _edges(client, hub)
    extra: dict[str, Any] = {"node_id": hub} if hub else {}

    everything = client.get(
        BASE, params={"sort": sort, "order": order, "limit": 100, **extra}
    ).json()
    seen = _walk(client, {"sort": sort, "order": order, "limit": 2, **extra})

    assert [e["id"] for e in seen] == [e["id"] for e in everything]
    assert {e["id"] for e in seen} == {e["id"] for e in created}
    assert len(seen) == len(created)

    def key(edge: dict[str, Any]) -> str:
        value: str = edge[sort]
        return value.lower() if sort == "type" else value

    values = [key(e) for e in seen]
    assert values == sorted(values, reverse=order == "desc")


def test_the_sort_keys_are_fields_of_the_connection_response() -> None:
    """A client sorts by what it sees."""
    assert {key.value for key in EdgeSort} <= set(EdgeResponse.model_fields)


def test_a_cursor_from_another_sort_or_an_unreadable_one_is_a_400() -> None:
    """The cursor has to match the request's sort and order."""
    client = TestClient(_app())
    _edges(client)
    first = client.get(BASE, params={"sort": "type", "limit": 1})

    mismatched = client.get(BASE, params={"after": _next_after(first.headers["Link"])})
    unreadable = client.get(BASE, params={"after": "nope"})

    assert mismatched.status_code == 400
    assert unreadable.status_code == 400


def test_connections_search_the_type() -> None:
    """`q` keeps the connections whose type contains it, whole list or one item."""
    client = TestClient(_app())
    hub = _node(client, "hub")
    _edges(client, hub)

    whole = client.get(BASE, params={"q": "OWN", "limit": 100}).json()
    one_item = client.get(
        BASE, params={"q": "like", "node_id": hub, "limit": 100}
    ).json()

    assert {e["type"] for e in whole} == {"owns"}
    assert len(whole) == 3
    assert {e["type"] for e in one_item} == {"likes"}
    assert len(one_item) == 2


def test_connections_say_how_many_match_for_the_whole_list_and_for_one_item() -> None:
    """`Total-Count` counts every connection, or only the ones touching `node_id`."""
    client = TestClient(_app())
    hub = _node(client, "hub")
    _edges(client, hub)
    _edges(client)

    whole = client.get(BASE, params={"limit": 2})
    one_item = client.get(BASE, params={"node_id": hub, "limit": 1})

    assert whole.headers["Total-Count"] == str(2 * len(TYPES))
    assert one_item.headers["Total-Count"] == str(len(TYPES))
