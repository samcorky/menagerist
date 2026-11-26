"""Sorting and paging of the item type, subtype and connection type lists."""

from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlparse

import pytest
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.modules.graph.adapters.api.dependencies import get_graph_repos, get_graph_uow
from app.modules.graph.adapters.api.edge_type.schemas import EdgeTypeResponse
from app.modules.graph.adapters.api.node_type.schemas import NodeTypeResponse
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
from app.modules.graph.application.list_edge_types import EdgeTypeSort
from app.modules.graph.application.list_node_types import NodeTypeSort
from app.modules.graph.ports.unit_of_work import GraphRepos

if TYPE_CHECKING:
    from fastapi import FastAPI

SLUGS = ["b", "A", "b-2", "c", "B-3", "a-4", "c-5"]


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


def _next_after(link: str) -> str:
    """The `after` cursor a `Link` header value points to."""
    url = link[link.index("<") + 1 : link.index(">")]
    return parse_qs(urlparse(url).query)["after"][0]


def _walk(client: TestClient, url: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    """Follow `Link` from the first page to the last, returning every row."""
    seen: list[dict[str, Any]] = []
    while True:
        response = client.get(url, params=params)
        assert response.status_code == 200
        seen.extend(response.json())
        if "Link" not in response.headers:
            return seen
        params = {**params, "after": _next_after(response.headers["Link"])}


def _slug(label: str) -> str:
    return label.lower().replace(" ", "-")


def _make_node_types(client: TestClient, parent: str | None = None) -> None:
    for slug in SLUGS:
        body = {"slug": _slug(slug), "label": slug.upper()}
        if parent is not None:
            body["parent"] = parent
        assert client.post("/api/v1/node-types", json=body).status_code == 201


def _make_edge_types(client: TestClient) -> None:
    for slug in SLUGS:
        body = {"slug": _slug(slug), "label": slug.upper(), "directional": True}
        assert client.post("/api/v1/edge-types", json=body).status_code == 201


def _check_order(rows: list[dict[str, Any]], sort: str, order: str) -> None:
    def key(row: dict[str, Any]) -> str:
        value: str = row[sort]
        return value.lower() if sort in {"slug", "label"} else value

    values = [key(row) for row in rows]
    assert values == sorted(values, reverse=order == "desc")


@pytest.mark.parametrize("order", ["asc", "desc"])
@pytest.mark.parametrize("sort", [key.value for key in NodeTypeSort])
def test_node_types_walk_every_sort_key_to_the_end(sort: str, order: str) -> None:
    """Following `Link` visits each item type once, in the order the key gives."""
    client = TestClient(_app())
    _make_node_types(client)
    url = "/api/v1/node-types"

    everything = client.get(url, params={"sort": sort, "order": order, "limit": 100})
    seen = _walk(client, url, {"sort": sort, "order": order, "limit": 2})

    assert [t["id"] for t in seen] == [t["id"] for t in everything.json()]
    assert len({t["id"] for t in seen}) == len(SLUGS)
    _check_order(seen, sort, order)


@pytest.mark.parametrize("order", ["asc", "desc"])
@pytest.mark.parametrize("sort", [key.value for key in EdgeTypeSort])
def test_edge_types_walk_every_sort_key_to_the_end(sort: str, order: str) -> None:
    """Following `Link` visits each connection type once, in the order the key gives."""
    client = TestClient(_app())
    _make_edge_types(client)
    url = "/api/v1/edge-types"

    everything = client.get(url, params={"sort": sort, "order": order, "limit": 100})
    seen = _walk(client, url, {"sort": sort, "order": order, "limit": 2})

    assert [t["id"] for t in seen] == [t["id"] for t in everything.json()]
    assert len({t["id"] for t in seen}) == len(SLUGS)
    _check_order(seen, sort, order)


@pytest.mark.parametrize("order", ["asc", "desc"])
@pytest.mark.parametrize("sort", [key.value for key in NodeTypeSort])
def test_subtypes_walk_every_sort_key_to_the_end(sort: str, order: str) -> None:
    """The subtypes of one parent page and sort like any other list."""
    client = TestClient(_app())
    parent = client.post(
        "/api/v1/node-types", json={"slug": "parent", "label": "Parent"}
    ).json()
    _make_node_types(client, parent="parent")
    url = f"/api/v1/node-types/{parent['id']}/subtypes"

    seen = _walk(client, url, {"sort": sort, "order": order, "limit": 2})

    assert len({t["id"] for t in seen}) == len(SLUGS)
    assert all(t["parent"] == "parent" for t in seen)
    _check_order(seen, sort, order)


def test_the_sort_keys_are_fields_of_the_responses() -> None:
    """A client sorts by what it sees."""
    assert {key.value for key in NodeTypeSort} <= set(NodeTypeResponse.model_fields)
    assert {key.value for key in EdgeTypeSort} <= set(EdgeTypeResponse.model_fields)


@pytest.mark.parametrize("url", ["/api/v1/node-types", "/api/v1/edge-types"])
def test_a_cursor_from_another_sort_or_an_unreadable_one_is_a_400(url: str) -> None:
    """The cursor has to match the request's sort and order."""
    client = TestClient(_app())
    _make_node_types(client)
    _make_edge_types(client)
    first = client.get(url, params={"sort": "label", "limit": 1})

    mismatched = client.get(url, params={"after": _next_after(first.headers["Link"])})
    unreadable = client.get(url, params={"after": "nope"})

    assert mismatched.status_code == 400
    assert unreadable.status_code == 400


def test_item_types_and_subtypes_search_label_slug_and_description() -> None:
    """`q` ignores case and accents and reads label, slug and description."""
    client = TestClient(_app())
    parent = client.post(
        "/api/v1/node-types", json={"slug": "memo", "label": "Memorabilia"}
    ).json()
    for slug, label, description in [
        ("poster", "Café poster", None),
        ("figure", "Figure", "A small CAFE statue"),
        ("mug", "Mug", None),
    ]:
        body: dict[str, Any] = {"slug": slug, "label": label, "parent": "memo"}
        if description:
            body["description"] = description
        assert client.post("/api/v1/node-types", json=body).status_code == 201

    by_label = client.get("/api/v1/node-types", params={"q": "CAFE"}).json()
    by_slug = client.get("/api/v1/node-types", params={"q": "ug"}).json()
    subtypes = client.get(
        f"/api/v1/node-types/{parent['id']}/subtypes", params={"q": "cafe"}
    ).json()

    assert sorted(t["slug"] for t in by_label) == ["figure", "poster"]
    assert [t["slug"] for t in by_slug] == ["mug"]
    assert sorted(t["slug"] for t in subtypes) == ["figure", "poster"]


def test_connection_types_search_label_reverse_label_slug_and_description() -> None:
    """Either direction's wording finds the type."""
    client = TestClient(_app())
    for slug, label, reverse, description in [
        ("owns", "Owns", "Owned by", None),
        ("likes", "Likes", None, "Taste, not ownership"),
    ]:
        body: dict[str, Any] = {"slug": slug, "label": label, "directional": True}
        if reverse:
            body["reverse_label"] = reverse
        if description:
            body["description"] = description
        assert client.post("/api/v1/edge-types", json=body).status_code == 201

    by_reverse = client.get("/api/v1/edge-types", params={"q": "owned"}).json()
    by_description = client.get("/api/v1/edge-types", params={"q": "TASTE"}).json()
    nothing = client.get("/api/v1/edge-types", params={"q": "zebra"}).json()

    assert [t["slug"] for t in by_reverse] == ["owns"]
    assert [t["slug"] for t in by_description] == ["likes"]
    assert nothing == []


def test_a_list_sorts_by_two_keys_in_their_own_directions_across_pages() -> None:
    """Repeated `sort` and `order` pair by position, and `Link` keeps all of them."""
    client = TestClient(_app())
    for slug, label in [("p", "Same"), ("q", "Same"), ("r", "Other"), ("s", "Same")]:
        body = {"slug": slug, "label": label}
        assert client.post("/api/v1/node-types", json=body).status_code == 201
    params = [
        ("sort", "label"),
        ("sort", "slug"),
        ("order", "asc"),
        ("order", "desc"),
        ("limit", "2"),
    ]

    pages = []
    after: str | None = None
    while True:
        response = client.get(
            "/api/v1/node-types",
            params=[*params, *([("after", after)] if after else [])],
        )
        assert response.status_code == 200
        pages.append([t["slug"] for t in response.json()])
        if "Link" not in response.headers:
            break
        link = response.headers["Link"]
        assert link.count("sort=") == 2
        after = _next_after(link)

    assert pages == [["r", "s"], ["q", "p"]]


def test_a_cursor_from_one_key_does_not_resume_a_list_of_two() -> None:
    """Changing the sort between pages is a 400, not a wrong page."""
    client = TestClient(_app())
    _make_node_types(client)
    first = client.get("/api/v1/node-types", params={"sort": "label", "limit": 2})
    cursor = _next_after(first.headers["Link"])

    response = client.get(
        "/api/v1/node-types",
        params=[("sort", "label"), ("sort", "slug"), ("after", cursor)],
    )

    assert response.status_code == 400
