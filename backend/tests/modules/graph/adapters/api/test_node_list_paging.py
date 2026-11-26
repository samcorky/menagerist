"""Sorting and paging of the items list."""

import unicodedata
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlparse

import pytest
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.modules.graph.adapters.api.dependencies import get_graph_repos, get_graph_uow
from app.modules.graph.adapters.api.node.schemas import NodeResponse
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
from app.modules.graph.application.list_nodes import NodeSort
from app.modules.graph.ports.unit_of_work import GraphRepos

if TYPE_CHECKING:
    from fastapi import FastAPI

BASE = "/api/v1/nodes"
ROWS = [
    ("banana", "film"),
    ("Apple", "book"),
    ("cherry", "film"),
    ("Éclair", "book"),
    ("Banana", "game"),
    ("apple", "film"),
    ("date", "book"),
]


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


def _create_all(client: TestClient) -> list[dict[str, Any]]:
    created = []
    for name, type_ in ROWS:
        response = client.post(BASE, json={"name": name, "type": type_})
        assert response.status_code == 201
        created.append(response.json())
    return created


def _fold(text: str) -> str:
    """Case and accents ignored, as the name sort does."""
    plain = "".join(
        c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c)
    )
    return plain.casefold()


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
@pytest.mark.parametrize("sort", [key.value for key in NodeSort])
def test_items_walk_every_sort_key_to_the_end(sort: str, order: str) -> None:
    """Following `Link` visits each item once, in the order the key gives."""
    client = TestClient(_app())
    created = _create_all(client)

    everything = client.get(
        BASE, params={"sort": sort, "order": order, "limit": 100}
    ).json()
    seen = _walk(client, {"sort": sort, "order": order, "limit": 2})

    assert [n["id"] for n in seen] == [n["id"] for n in everything]
    assert {n["id"] for n in seen} == {n["id"] for n in created}
    assert len(seen) == len(created)
    values = [_fold(n[sort]) if sort in {"name", "type"} else n[sort] for n in seen]
    assert values == sorted(values, reverse=order == "desc")


def test_items_sort_by_name_ignores_case_and_accents() -> None:
    """Éclair sits between date and the Fs, and equal names keep creation order."""
    client = TestClient(_app())
    _create_all(client)

    names = [n["name"] for n in client.get(BASE, params={"sort": "name"}).json()]

    assert names == ["Apple", "apple", "banana", "Banana", "cherry", "date", "Éclair"]


def test_order_desc_alone_lists_the_newest_first() -> None:
    """With no `sort`, `order=desc` reverses the creation order."""
    client = TestClient(_app())
    created = _create_all(client)

    newest_first = client.get(BASE, params={"order": "desc"}).json()

    assert [n["id"] for n in newest_first] == [n["id"] for n in reversed(created)]


def test_filters_still_apply_while_sorting_and_paging() -> None:
    """`type` and `q` narrow the list, and the cursor pages only what is left."""
    client = TestClient(_app())
    _create_all(client)

    films = _walk(client, {"type": "film", "sort": "name", "limit": 1})
    found = _walk(client, {"q": "app", "sort": "name", "limit": 1})

    assert {n["type"] for n in films} == {"film"}
    assert len(films) == 3
    assert [n["name"].lower() for n in found] == ["apple", "apple"]


def test_the_sort_keys_are_fields_of_the_item_response() -> None:
    """A client sorts by what it sees."""
    assert {key.value for key in NodeSort} <= set(NodeResponse.model_fields)


def test_a_cursor_from_another_sort_or_an_unreadable_one_is_a_400() -> None:
    """The cursor has to match the request's sort and order."""
    client = TestClient(_app())
    _create_all(client)
    first = client.get(BASE, params={"sort": "type", "limit": 1})

    mismatched = client.get(BASE, params={"after": _next_after(first.headers["Link"])})
    unreadable = client.get(BASE, params={"after": "nope"})

    assert mismatched.status_code == 400
    assert unreadable.status_code == 400
