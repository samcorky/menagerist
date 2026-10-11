"""Media and graph through the real app and Postgres, with two people."""

import uuid
from typing import TYPE_CHECKING, Any

import pytest
import sqlalchemy
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.modules.media.adapters.api.dependencies import get_media_storage
from app.modules.media.adapters.storage.in_memory_media_storage import (
    InMemoryMediaStorage,
)
from app.platform.database import get_engine, get_session_factory

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from fastapi import FastAPI

pytestmark = pytest.mark.integration

ALICE = uuid.UUID(int=101)
BOB = uuid.UUID(int=102)
PDF = ("a.pdf", b"%PDF-1.4 test", "application/pdf")


def _wipe(sync_url: str) -> None:
    """Remove what the test committed; the database is shared across the session."""
    engine = sqlalchemy.create_engine(sync_url)
    with engine.begin() as connection:
        for table in ("media_attachments", "media_assets", "edges", "nodes"):
            connection.execute(sqlalchemy.text(f"DELETE FROM {table}"))
    engine.dispose()


@pytest.fixture
def app(postgres_url: str, postgres_sync_url: str) -> Iterator[FastAPI]:
    """The real app on Postgres with in-memory file storage."""
    get_session_factory.cache_clear()
    get_engine.cache_clear()
    application = create_app()
    storage = InMemoryMediaStorage()
    application.dependency_overrides[get_media_storage] = lambda: storage
    try:
        yield application
    finally:
        get_session_factory.cache_clear()
        get_engine.cache_clear()
        _wipe(postgres_sync_url)


def _create_item(client: TestClient) -> str:
    response = client.post("/api/v1/node", json={"name": "Alien"})
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return str(created["id"])


def test_attaching_needs_a_visible_item_through_the_real_bridge(
    app: FastAPI, as_user: Callable[..., None]
) -> None:
    """Own item works; another person's item is a 404 and stores nothing."""
    with TestClient(app) as client:
        as_user(app, ALICE)
        item = _create_item(client)
        data = {"target_type": "node", "target_id": item}

        as_user(app, BOB)
        refused = client.post("/api/v1/media/attached", data=data, files={"file": PDF})
        assert refused.status_code == 404, refused.text
        assert client.get(f"/api/v1/media/for-node/{item}").json() == []

        as_user(app, ALICE)
        accepted = client.post("/api/v1/media/attached", data=data, files={"file": PDF})
        assert accepted.status_code == 201, accepted.text
        asset_id = accepted.json()["asset_id"]
        listed = client.get(f"/api/v1/media/for-node/{item}").json()
        assert [row["id"] for row in listed] == [asset_id]

        as_user(app, BOB)
        assert client.get(f"/api/v1/media/for-node/{item}").json() == []
        assert client.get(f"/api/v1/media/{asset_id}").status_code == 404
        assert client.get(f"/api/v1/media/{asset_id}/content").status_code == 404
