"""Two people install the same pack through the real app on Postgres."""

import json
import uuid
from typing import TYPE_CHECKING, Any

import pytest
import sqlalchemy
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.dependencies import get_current_actor
from app.modules.examples.adapters.api.dependencies import get_pack_catalogue
from app.modules.examples.adapters.platform.file_pack_catalogue import FilePackCatalogue
from app.modules.media.adapters.api.dependencies import get_media_storage
from app.modules.media.adapters.storage.local_filesystem import (
    LocalFilesystemMediaStorage,
)
from app.platform.database import get_engine, get_session_factory
from app.shared_kernel.actor import Actor

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

pytestmark = pytest.mark.integration

ALICE = Actor(id=uuid.UUID(int=0xA1), roles=frozenset({"member"}))
BOB = Actor(id=uuid.UUID(int=0xB2), roles=frozenset({"member"}))
_INSTALL = "/api/v1/examples/demo/installation"

_PACK: dict[str, Any] = {
    "format": "menagerist-example-pack",
    "version": 3,
    "id": "demo",
    "relationship_types": [
        {"ref": "by", "slug": "demo-by", "label": "By", "reverse_label": "Made"}
    ],
    "item_types": [
        {
            "ref": "thing",
            "slug": "demo-thing",
            "label": "Thing",
            "cover": {"style": "sleeve"},
        }
    ],
    "items": [
        {"ref": "a", "type": "thing", "name": "A"},
        {"ref": "b", "type": "thing", "name": "B"},
    ],
    "connections": [{"from": "a", "to": "b", "type": "by"}],
    "collections": [{"ref": "duo", "name": "Duo", "items": ["a", "b"]}],
}


def _wipe(sync_url: str) -> None:
    engine = sqlalchemy.create_engine(sync_url)
    with engine.begin() as connection:
        for table in (
            "media_attachments",
            "media_assets",
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


class _Who:
    """The signed-in person for the next requests."""

    def __init__(self) -> None:
        self.actor = ALICE


@pytest.fixture
def who() -> _Who:
    """Switch the signed-in person by setting `who.actor`."""
    return _Who()


@pytest.fixture
def client(
    postgres_url: str, postgres_sync_url: str, tmp_path: Path, who: _Who
) -> Iterator[TestClient]:
    """The real app on Postgres serving one pack, acting as `who.actor`."""
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
    app.dependency_overrides[get_current_actor] = lambda: who.actor
    app.dependency_overrides[get_pack_catalogue] = lambda: FilePackCatalogue(tmp_path)
    storage = LocalFilesystemMediaStorage(tmp_path / "media")
    app.dependency_overrides[get_media_storage] = lambda: storage
    try:
        with TestClient(app) as c:
            yield c
    finally:
        get_session_factory.cache_clear()
        get_engine.cache_clear()
        _wipe(postgres_sync_url)


def _owners(sync_url: str, table: str) -> list[uuid.UUID]:
    engine = sqlalchemy.create_engine(sync_url)
    with engine.connect() as connection:
        rows = connection.execute(
            sqlalchemy.text(f"SELECT owner_id FROM {table} ORDER BY owner_id")
        ).scalars()
        owners = list(rows)
    engine.dispose()
    return owners


def test_both_people_install_and_remove_with_their_own_types(
    client: TestClient, who: _Who, postgres_sync_url: str
) -> None:
    """Own content, covers and types each, removed independently."""
    who.actor = ALICE
    assert client.put(_INSTALL).status_code == 200
    who.actor = BOB
    second = client.put(_INSTALL)
    assert second.status_code == 200, second.text
    assert second.json()["created"]["item_types"] == 1
    assert second.json()["created"]["items"] == 2

    for table in ("node_types", "nodes", "edges", "collections", "media_assets"):
        owners = _owners(postgres_sync_url, table)
        assert set(owners) == {ALICE.id, BOB.id}, table
    assert len(_owners(postgres_sync_url, "example_installations")) == 2
    assert len(client.get("/api/v1/nodes?limit=100").json()) == 2
    assert len(client.get("/api/v1/collections").json()) == 1
    assert len(client.get("/api/v1/node-types").json()) == 1

    who.actor = ALICE
    left = client.delete(_INSTALL)
    assert left.status_code == 200, left.text
    assert left.json()["removed"]["items"] == 2
    assert client.get("/api/v1/node-types").json() == []
    who.actor = BOB
    assert len(client.get("/api/v1/nodes?limit=100").json()) == 2
    assert len(client.get("/api/v1/node-types").json()) == 1

    assert client.delete(_INSTALL).status_code == 200
    assert client.get("/api/v1/node-types").json() == []
    assert client.get("/api/v1/edge-types").json() == []
    assert _owners(postgres_sync_url, "media_assets") == []


def test_people_cannot_see_each_others_installations_or_example_ids(
    client: TestClient, who: _Who
) -> None:
    """Bob sees no installation or example ids and cannot remove Alice's pack."""
    who.actor = ALICE
    client.put(_INSTALL)
    who.actor = BOB

    listed = client.get("/api/v1/examples").json()
    entities = client.get("/api/v1/examples/entities").json()

    assert listed[0]["installation"] is None
    assert entities == {"item_ids": [], "item_type_ids": [], "collection_ids": []}
    assert client.delete(_INSTALL).status_code == 409
    who.actor = ALICE
    assert len(client.get("/api/v1/examples/entities").json()["item_ids"]) == 2


def test_the_installers_own_item_keeps_their_type_through_removal(
    client: TestClient, who: _Who
) -> None:
    """Alice's own item of a pack type survives her removal, and keeps the type."""
    who.actor = ALICE
    assert client.put(_INSTALL).status_code == 200
    made = client.post("/api/v1/nodes", json={"name": "Mine", "type": "demo-thing"})
    assert made.status_code == 201, made.text

    left = client.delete(_INSTALL)

    assert left.status_code == 200, left.text
    assert ("item_type", "still in use") in {
        (k["kind"], k["reason"]) for k in left.json()["kept"]
    }
    assert [n["name"] for n in client.get("/api/v1/nodes?limit=100").json()] == ["Mine"]
    assert [t["slug"] for t in client.get("/api/v1/node-types").json()] == [
        "demo-thing"
    ]


def test_a_type_with_the_packs_slug_only_blocks_its_own_owner(
    client: TestClient, who: _Who
) -> None:
    """Bob's own type of that name does not stop Alice; Alice's would stop Alice."""
    who.actor = BOB
    made = client.post(
        "/api/v1/node-types", json={"slug": "demo-thing", "label": "Mine"}
    )
    assert made.status_code == 201, made.text

    who.actor = ALICE
    assert client.put(_INSTALL).status_code == 200
    assert client.delete(_INSTALL).status_code == 200
    made = client.post(
        "/api/v1/node-types", json={"slug": "demo-thing", "label": "Mine"}
    )
    assert made.status_code == 201, made.text

    assert client.put(_INSTALL).status_code == 409
