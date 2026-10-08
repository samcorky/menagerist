"""End-to-end test of collections and graph through the real app on Postgres."""

from typing import TYPE_CHECKING, Any

import pytest
import sqlalchemy
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.platform.database import get_engine, get_session_factory

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = pytest.mark.integration


def _wipe(sync_url: str) -> None:
    """Remove what the test committed; the database is shared across the session."""
    engine = sqlalchemy.create_engine(sync_url)
    with engine.begin() as connection:
        for table in ("collection_members", "collections", "edges", "nodes"):
            connection.execute(sqlalchemy.text(f"DELETE FROM {table}"))
        connection.execute(sqlalchemy.text("DELETE FROM node_types"))
    engine.dispose()


@pytest.fixture
def client(postgres_url: str, postgres_sync_url: str) -> Iterator[TestClient]:
    """An in-process client on the real app and Postgres, with a fresh engine."""
    get_session_factory.cache_clear()
    get_engine.cache_clear()
    try:
        with TestClient(create_app()) as c:
            yield c
    finally:
        get_session_factory.cache_clear()
        get_engine.cache_clear()
        _wipe(postgres_sync_url)


def _create(client: TestClient, path: str, body: dict[str, Any]) -> dict[str, Any]:
    response = client.post(path, json=body)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


def test_collection_lists_exactly_its_items_through_the_real_bridges(
    client: TestClient,
) -> None:
    """Items put on a collection are listed, counted and filtered by it."""
    _create(client, "/api/v1/node-type", {"slug": "film", "label": "Film"})
    names = ["Alien", "Aliens", "Heat", "Ronin"]
    items = {
        name: _create(client, "/api/v1/node", {"name": name, "type": "film"})["id"]
        for name in names
    }
    shelf = _create(client, "/api/v1/collection", {"name": "Shelf"})
    base = f"/api/v1/collection/{shelf['id']}"

    put = client.put(
        f"{base}/item",
        json={"item_ids": [items["Alien"], items["Aliens"], items["Heat"]]},
    )
    assert put.status_code == 200, put.text

    listed = client.get(f"/api/v1/node?collection={shelf['id']}")
    assert listed.status_code == 200
    assert {n["id"] for n in listed.json()} == {
        items["Alien"],
        items["Aliens"],
        items["Heat"],
    }
    assert listed.headers["Total-Count"] == "3"

    searched = client.get(f"/api/v1/node?collection={shelf['id']}&q=alien")
    assert {n["name"] for n in searched.json()} == {"Alien", "Aliens"}
    assert searched.headers["Total-Count"] == "2"

    assert client.get(base).json()["item_count"] == 3

    assert client.delete(f"/api/v1/node/{items['Heat']}").status_code == 204
    assert client.get(base).json()["item_count"] == 2
    after_delete = client.get(f"/api/v1/node?collection={shelf['id']}")
    assert {n["name"] for n in after_delete.json()} == {"Alien", "Aliens"}
    assert after_delete.headers["Total-Count"] == "2"

    rejected = client.put(f"{base}/item", json={"item_ids": [items["Heat"]]})
    assert rejected.status_code == 400

    assert client.delete(base).status_code == 204
    gone = client.get(f"/api/v1/node?collection={shelf['id']}")
    assert gone.status_code == 404
