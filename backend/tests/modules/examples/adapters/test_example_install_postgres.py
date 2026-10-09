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


def _wipe(sync_url: str) -> None:
    """Remove what the test committed; the database is shared across the session."""
    engine = sqlalchemy.create_engine(sync_url)
    with engine.begin() as connection:
        for table in ("edges", "nodes", "node_types", "edge_types"):
            connection.execute(sqlalchemy.text(f"DELETE FROM {table}"))
        connection.execute(sqlalchemy.text("DELETE FROM example_installations"))
        connection.execute(sqlalchemy.text("DELETE FROM presets WHERE NOT builtin"))
    engine.dispose()


@pytest.fixture
def client(
    postgres_url: str,
    postgres_sync_url: str,
    tmp_path: Path,
    pack_data: dict[str, Any],
) -> Iterator[TestClient]:
    """An in-process client on the real app, dependencies and Postgres.

    The process-wide engine is cached, and asyncpg connections belong to one event
    loop. Entering `TestClient` keeps one loop for the whole test, and the caches are
    reset so that loop builds its own engine.
    """
    index = {
        "format": "menagerist-examples-index",
        "version": 1,
        "packs": [{"id": "demo", "name": "Demo", "description": "A tiny pack."}],
    }
    (tmp_path / "index.json").write_text(json.dumps(index), encoding="utf-8")
    (tmp_path / "demo.json").write_text(json.dumps(pack_data), encoding="utf-8")
    get_session_factory.cache_clear()
    get_engine.cache_clear()
    app = create_app()
    app.dependency_overrides[get_pack_catalogue] = lambda: FilePackCatalogue(tmp_path)
    try:
        with TestClient(app) as c:
            yield c
    finally:
        # The cached async engine is dropped with its loop; its pool is not disposed.
        get_session_factory.cache_clear()
        get_engine.cache_clear()
        _wipe(postgres_sync_url)


def test_install_uninstall_and_reinstall_on_postgres(
    client: TestClient,
) -> None:
    """A pack installs, lists, removes cleanly and installs again on Postgres."""
    first = client.put("/api/v1/example/demo/installation")
    assert first.status_code == 200, first.text
    assert first.json()["created"]["items"] == 2
    assert first.json()["adopted"]["items"] == 0

    listed = client.get("/api/v1/example").json()
    assert listed[0]["installation"]["status"] == "installed"
    assert len(client.get("/api/v1/node-type").json()) == 1

    removed = client.delete("/api/v1/example/demo/installation")
    assert removed.status_code == 200, removed.text
    assert removed.json()["kept"] == []
    assert client.get("/api/v1/node-type").json() == []

    again = client.put("/api/v1/example/demo/installation")
    assert again.status_code == 200, again.text
    client.delete("/api/v1/example/demo/installation")


def test_reinstall_adopts_an_edited_item_on_postgres(client: TestClient) -> None:
    """A removal keeps an edited item and its type; the next install takes them back."""
    assert client.put("/api/v1/example/demo/installation").status_code == 200
    items = {n["name"]: n for n in client.get("/api/v1/node?limit=100").json()}
    patched = client.patch(
        f"/api/v1/node/{items['A']['id']}",
        json={"name": "Mine"},
    )
    assert patched.status_code == 200, patched.text
    removed = client.delete("/api/v1/example/demo/installation").json()
    assert {(k["kind"], k["reason"]) for k in removed["kept"]} >= {
        ("item", "edited"),
        ("item_type", "still in use"),
    }

    again = client.put("/api/v1/example/demo/installation")

    assert again.status_code == 200, again.text
    body = again.json()
    assert (body["adopted"]["items"], body["adopted"]["item_types"]) == (1, 1)
    assert (body["created"]["items"], body["created"]["item_types"]) == (1, 0)
    names = sorted(n["name"] for n in client.get("/api/v1/node?limit=100").json())
    assert names == ["B", "Mine"]
    assert len(client.get("/api/v1/node-type").json()) == 1
    # Still protected: another removal keeps the edited item.
    second = client.delete("/api/v1/example/demo/installation").json()
    assert ("item", "A", "edited") in {
        (k["kind"], k["label"], k["reason"]) for k in second["kept"]
    }
