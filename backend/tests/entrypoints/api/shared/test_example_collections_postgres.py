"""Example packs with collections, end to end through the real app on Postgres."""

import json
from typing import TYPE_CHECKING, Any

import pytest
import sqlalchemy
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.modules.examples.adapters.api.dependencies import get_pack_catalogue
from app.modules.examples.adapters.platform.file_pack_catalogue import FilePackCatalogue
from app.platform.database import get_engine, get_session_factory

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

pytestmark = pytest.mark.integration

_INSTALL = "/api/v1/example/demo/installation"
_PACK: dict[str, Any] = {
    "format": "menagerist-example-pack",
    "version": 2,
    "id": "demo",
    "item_types": [{"ref": "thing", "slug": "thing", "label": "Thing"}],
    "items": [
        {"ref": "a", "type": "thing", "name": "A"},
        {"ref": "b", "type": "thing", "name": "B"},
        {"ref": "c", "type": "thing", "name": "C"},
    ],
    "collections": [
        {"ref": "duo", "name": "Duo", "description": "Two things", "items": ["a", "b"]},
        {"ref": "solo", "name": "Solo", "items": ["c"]},
    ],
}


_DUO_EDITED = ("collection", "Duo", "edited")
_A_HELD = ("item", "A", "has your connections, files or collections")
_B_HELD = ("item", "B", "has your connections, files or collections")
_TYPE_IN_USE = ("item_type", "Thing", "still in use")


def _wipe(sync_url: str) -> None:
    """Remove what the test committed; the database is shared across the session."""
    engine = sqlalchemy.create_engine(sync_url)
    with engine.begin() as connection:
        for table in (
            "collection_members",
            "collections",
            "edges",
            "nodes",
            "node_types",
            "edge_types",
            "example_installations",
        ):
            connection.execute(sqlalchemy.text(f"DELETE FROM {table}"))
    engine.dispose()


@pytest.fixture
def client(
    postgres_url: str, postgres_sync_url: str, tmp_path: Path
) -> Iterator[TestClient]:
    """An in-process client on the real app and Postgres, serving a v2 demo pack."""
    index = {
        "format": "menagerist-examples-index",
        "version": 1,
        "packs": [{"id": "demo", "name": "Demo", "description": "A tiny pack."}],
    }
    (tmp_path / "index.json").write_text(json.dumps(index), encoding="utf-8")
    (tmp_path / "demo.json").write_text(json.dumps(_PACK), encoding="utf-8")
    get_session_factory.cache_clear()
    get_engine.cache_clear()
    app = create_app()
    app.dependency_overrides[get_pack_catalogue] = lambda: FilePackCatalogue(tmp_path)
    try:
        with TestClient(app) as c:
            yield c
    finally:
        get_session_factory.cache_clear()
        get_engine.cache_clear()
        _wipe(postgres_sync_url)


def _install(client: TestClient) -> dict[str, Any]:
    response = client.put(_INSTALL)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _uninstall(client: TestClient) -> dict[str, Any]:
    response = client.delete(_INSTALL)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _collections(client: TestClient) -> dict[str, dict[str, Any]]:
    response = client.get("/api/v1/collection")
    assert response.status_code == 200, response.text
    return {c["name"]: c for c in response.json()}


def _items(client: TestClient) -> dict[str, str]:
    response = client.get("/api/v1/node?limit=100")
    assert response.status_code == 200, response.text
    return {n["name"]: n["id"] for n in response.json()}


def _members(client: TestClient, collection_id: str) -> set[str]:
    response = client.get(f"/api/v1/node?collection={collection_id}")
    assert response.status_code == 200, response.text
    return {n["name"] for n in response.json()}


def _own_collection(client: TestClient, name: str, item_ids: list[str]) -> str:
    created = client.post("/api/v1/collection", json={"name": name})
    assert created.status_code == 201, created.text
    collection_id: str = created.json()["id"]
    put = client.put(
        f"/api/v1/collection/{collection_id}/item", json={"item_ids": item_ids}
    )
    assert put.status_code == 200, put.text
    return collection_id


def _kept(result: dict[str, Any]) -> set[tuple[str, str, str]]:
    return {(k["kind"], k["label"], k["reason"]) for k in result["kept"]}


def test_install_creates_collections_with_members_and_slugs(
    client: TestClient,
) -> None:
    """Collections exist with their members, derived slugs and the counts."""
    result = _install(client)

    assert result["created"]["collections"] == 2
    collections = _collections(client)
    assert set(collections) == {"Duo", "Solo"}
    assert collections["Duo"]["slug"] == "duo"
    assert collections["Duo"]["description"] == "Two things"
    assert collections["Duo"]["item_count"] == 2
    assert _members(client, collections["Duo"]["id"]) == {"A", "B"}
    assert _members(client, collections["Solo"]["id"]) == {"C"}
    listed = client.get("/api/v1/example").json()
    assert listed[0]["installation"]["counts"]["collections"] == 2


def test_entities_lists_the_collection_ids(client: TestClient) -> None:
    """`GET /example/entities` lists the example collections, and none once removed."""
    _install(client)
    collections = _collections(client)

    body = client.get("/api/v1/example/entities").json()

    assert set(body["collection_ids"]) == {c["id"] for c in collections.values()}
    assert len(body["item_ids"]) == 3

    _uninstall(client)
    assert client.get("/api/v1/example/entities").json()["collection_ids"] == []


def test_uninstalling_an_untouched_install_removes_everything(
    client: TestClient,
) -> None:
    """Collections, items and the type all go, and the counts say so."""
    _install(client)

    result = _uninstall(client)

    assert result["kept"] == []
    assert result["removed"]["collections"] == 2
    assert _collections(client) == {}
    assert _items(client) == {}
    assert client.get("/api/v1/node-type").json() == []


def test_a_renamed_collection_is_kept_with_its_items(client: TestClient) -> None:
    """Renaming an example collection keeps it and its members; the rest goes."""
    _install(client)
    duo = _collections(client)["Duo"]
    renamed = client.patch(f"/api/v1/collection/{duo['id']}", json={"name": "Mine"})
    assert renamed.status_code == 200, renamed.text

    result = _uninstall(client)

    assert _kept(result) == {_DUO_EDITED, _A_HELD, _B_HELD, _TYPE_IN_USE}
    assert (result["removed"]["items"], result["removed"]["collections"]) == (1, 1)
    collections = _collections(client)
    assert set(collections) == {"Mine"}
    assert _members(client, duo["id"]) == {"A", "B"}
    assert set(_items(client)) == {"A", "B"}


def test_an_item_on_the_users_own_collection_is_kept(client: TestClient) -> None:
    """The item stays on the user's collection; unedited example ones are removed."""
    _install(client)
    items = _items(client)
    mine = _own_collection(client, "Favourites", [items["C"]])

    result = _uninstall(client)

    assert [k for k in result["kept"] if k["kind"] == "collection"] == []
    assert [(k["label"]) for k in result["kept"] if k["kind"] == "item"] == ["C"]
    assert set(_collections(client)) == {"Favourites"}
    assert _members(client, mine) == {"C"}
    assert set(_items(client)) == {"C"}


def test_a_users_item_added_to_an_example_collection_keeps_it(
    client: TestClient,
) -> None:
    """Adding the user's own item makes the example collection edited, so it stays."""
    _install(client)
    client.post("/api/v1/node-type", json={"slug": "own", "label": "Own"})
    own = client.post("/api/v1/node", json={"name": "Mine", "type": "own"}).json()
    duo = _collections(client)["Duo"]
    put = client.put(
        f"/api/v1/collection/{duo['id']}/item", json={"item_ids": [own["id"]]}
    )
    assert put.status_code == 200, put.text

    result = _uninstall(client)

    assert _kept(result) == {_DUO_EDITED, _A_HELD, _B_HELD, _TYPE_IN_USE}
    assert (result["removed"]["items"], result["removed"]["collections"]) == (1, 1)
    assert set(_collections(client)) == {"Duo"}
    assert _members(client, duo["id"]) == {"A", "B", "Mine"}
    assert set(_items(client)) == {"A", "B", "Mine"}


def test_deleting_an_example_item_makes_its_collection_look_edited(
    client: TestClient,
) -> None:
    """A user-deleted member changes the stored membership, so the collection stays."""
    _install(client)
    items = _items(client)
    assert client.delete(f"/api/v1/node/{items['B']}").status_code == 204

    result = _uninstall(client)

    assert _kept(result) == {_DUO_EDITED, _A_HELD, _TYPE_IN_USE}
    assert (result["removed"]["items"], result["removed"]["collections"]) == (2, 1)
    collections = _collections(client)
    assert set(collections) == {"Duo"}
    assert collections["Duo"]["item_count"] == 1
    assert _members(client, collections["Duo"]["id"]) == {"A"}
    assert set(_items(client)) == {"A"}


def test_reinstalling_adopts_a_kept_collection_as_the_user_left_it(
    client: TestClient,
) -> None:
    """An emptied, kept collection is taken back untouched; the other is created."""
    _install(client)
    duo = _collections(client)["Duo"]
    # Emptied by the user: edited, so kept, but it holds no items (and so no type).
    for item_id in _items(client).values():
        client.delete(f"/api/v1/collection/{duo['id']}/item/{item_id}")
    _uninstall(client)
    assert set(_collections(client)) == {"Duo"}
    assert _items(client) == {}

    again = _install(client)

    assert again["adopted"]["collections"] == 1
    assert again["created"]["collections"] == 1
    listed = client.get("/api/v1/collection").json()
    assert sorted(c["slug"] for c in listed) == ["duo", "solo"]
    assert next(c for c in listed if c["slug"] == "duo")["id"] == duo["id"]
    assert _members(client, duo["id"]) == set()


def test_reinstalling_after_keeping_an_edited_collection_adopts_it(
    client: TestClient,
) -> None:
    """Kept items, their type and the edited collection are reused, not duplicated."""
    _install(client)
    duo = _collections(client)["Duo"]
    client.patch(f"/api/v1/collection/{duo['id']}", json={"name": "Mine"})
    _uninstall(client)
    kept_items = _items(client)

    again = _install(client)

    assert again["adopted"] == {
        "presets": 0,
        "relationship_types": 0,
        "item_types": 1,
        "items": 2,
        "connections": 0,
        "collections": 1,
    }
    assert (again["created"]["items"], again["created"]["collections"]) == (1, 1)
    assert set(_collections(client)) == {"Mine", "Solo"}
    items = _items(client)
    assert {k: items[k] for k in ("A", "B")} == kept_items
    assert set(items) == {"A", "B", "C"}
    assert _members(client, duo["id"]) == {"A", "B"}
    assert len(client.get("/api/v1/node-type").json()) == 1
    # The adopted collection is left as the user has it; Solo is the pack's again.
    assert len(client.get("/api/v1/example/entities").json()["collection_ids"]) == 2
