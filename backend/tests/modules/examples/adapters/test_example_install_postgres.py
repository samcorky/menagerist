import io
import json
from typing import TYPE_CHECKING, Annotated, Any, cast

import pytest
import sqlalchemy
from fastapi import Depends
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker  # noqa: TC002
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.example_targets import (
    CoverPackTarget,
    build_cover_stores,
    get_cover_pack_target,
)
from app.modules.examples.adapters.api.dependencies import get_pack_catalogue
from app.modules.examples.adapters.covers.pillow_cover_renderer import (
    PillowCoverRenderer,
)
from app.modules.examples.adapters.platform.file_pack_catalogue import FilePackCatalogue
from app.modules.examples.domain.errors import InstallFailedError
from app.modules.examples.ports.pack_targets import Created  # noqa: TC001
from app.modules.media.adapters.api.dependencies import get_media_storage
from app.modules.media.adapters.imaging.pillow_processor import PillowImageProcessor
from app.modules.media.adapters.policy.content_type_attachment_policy import (
    ContentTypeAttachmentPolicy,
)
from app.modules.media.adapters.storage.local_filesystem import (
    LocalFilesystemMediaStorage,
)
from app.modules.media.ports.media_storage import MediaStoragePort  # noqa: TC001
from app.platform.database import get_engine, get_session_factory

if TYPE_CHECKING:
    import uuid
    from collections.abc import Iterator
    from pathlib import Path

    from fastapi import FastAPI

pytestmark = pytest.mark.integration


def _wipe(sync_url: str) -> None:
    """Remove what the test committed; the database is shared across the session."""
    engine = sqlalchemy.create_engine(sync_url)
    with engine.begin() as connection:
        for table in (
            "media_attachments",
            "media_assets",
            "edges",
            "nodes",
            "node_types",
            "edge_types",
        ):
            connection.execute(sqlalchemy.text(f"DELETE FROM {table}"))
        connection.execute(sqlalchemy.text("DELETE FROM example_installations"))
        connection.execute(sqlalchemy.text("DELETE FROM presets WHERE NOT builtin"))
    engine.dispose()


@pytest.fixture
def media_dir(tmp_path: Path) -> Path:
    """Where the real media storage writes in these tests."""
    return tmp_path / "media"


def _own_png() -> bytes:
    """A real image of the person's own."""
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (200, 30, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


def _media_state(sync_url: str, media_dir: Path) -> tuple[int, int, int]:
    """Return (assets, attachments, stored files incl. thumbnails)."""
    engine = sqlalchemy.create_engine(sync_url)
    with engine.connect() as connection:
        assets = connection.execute(
            sqlalchemy.text("SELECT count(*) FROM media_assets")
        ).scalar_one()
        attachments = connection.execute(
            sqlalchemy.text("SELECT count(*) FROM media_attachments")
        ).scalar_one()
    engine.dispose()
    return assets, attachments, sum(1 for f in media_dir.rglob("*") if f.is_file())


@pytest.fixture
def client(
    postgres_url: str,
    postgres_sync_url: str,
    tmp_path: Path,
    media_dir: Path,
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
        "packs": [
            {"id": "demo", "name": "Demo", "description": "A tiny pack."},
            {"id": "tune", "name": "Tune", "description": "A non-ASCII name."},
        ],
    }
    tune = {
        "format": "menagerist-example-pack",
        "version": 3,
        "id": "tune",
        "item_types": [
            {"ref": "song", "slug": "song", "label": "Song", "cover": {"style": "card"}}
        ],
        "items": [{"ref": "s", "type": "song", "name": "Łódź 🎵"}],
    }
    (tmp_path / "tune.json").write_text(json.dumps(tune), encoding="utf-8")
    (tmp_path / "index.json").write_text(json.dumps(index), encoding="utf-8")
    pack_data["version"] = 3
    pack_data["item_types"][0]["cover"] = {"style": "sleeve"}
    (tmp_path / "demo.json").write_text(json.dumps(pack_data), encoding="utf-8")
    get_session_factory.cache_clear()
    get_engine.cache_clear()
    app = create_app()
    app.dependency_overrides[get_pack_catalogue] = lambda: FilePackCatalogue(tmp_path)
    storage = LocalFilesystemMediaStorage(media_dir)
    app.dependency_overrides[get_media_storage] = lambda: storage
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


def test_covers_are_attached_then_removed_without_leaving_media_behind(
    client: TestClient, postgres_sync_url: str, media_dir: Path
) -> None:
    """Two covered items: two assets, attachments and files (plus thumbnails)."""
    assert client.put("/api/v1/example/demo/installation").status_code == 200

    assets, attachments, files = _media_state(postgres_sync_url, media_dir)
    assert (assets, attachments) == (2, 2)
    assert files >= 2  # the images, and a thumbnail beside each
    items = client.get("/api/v1/node?limit=100").json()
    assert len(items) == 2
    for item in items:
        media = client.get(f"/api/v1/media/for-node/{item['id']}").json()
        assert [m["attribute_key"] for m in media] == ["cover"]

    removed = client.delete("/api/v1/example/demo/installation")

    assert removed.status_code == 200, removed.text
    assert removed.json()["kept"] == []
    assert _media_state(postgres_sync_url, media_dir) == (0, 0, 0)


def test_a_replaced_cover_survives_removal_with_its_item(
    client: TestClient, postgres_sync_url: str, media_dir: Path
) -> None:
    """Swapping in the person's own image keeps that item, and only that item."""
    assert client.put("/api/v1/example/demo/installation").status_code == 200
    items = {n["name"]: n for n in client.get("/api/v1/node?limit=100").json()}
    target = {"target_type": "node", "target_id": items["A"]["id"]}
    mine = client.post(
        "/api/v1/media/attached",
        data=target,
        files={"file": ("mine.png", _own_png(), "image/png")},
    )
    assert mine.status_code == 201, mine.text
    set_cover = client.post(
        f"/api/v1/media/{mine.json()['asset_id']}/attachments/cover", json=target
    )
    assert set_cover.status_code == 200, set_cover.text

    removed = client.delete("/api/v1/example/demo/installation").json()

    assert ("item", "A", "has your connections, files or collections") in {
        (k["kind"], k["label"], k["reason"]) for k in removed["kept"]
    }
    assert all(k["kind"] != "cover" for k in removed["kept"])
    assert [n["name"] for n in client.get("/api/v1/node?limit=100").json()] == ["A"]
    assets, attachments, _ = _media_state(postgres_sync_url, media_dir)
    assert (assets, attachments) == (2, 2)  # the pack's image stays beside theirs

    again = client.put("/api/v1/example/demo/installation")

    assert again.status_code == 200, again.text
    assert again.json()["adopted"]["items"] == 1
    assert _media_state(postgres_sync_url, media_dir)[:2] == (3, 3)  # only B is new


def test_a_cover_for_a_non_latin1_item_name_can_be_fetched(client: TestClient) -> None:
    """The asset filename carries the name, and its headers must still encode."""
    assert client.put("/api/v1/example/tune/installation").status_code == 200
    [item] = client.get("/api/v1/node?limit=100").json()
    [media] = client.get(f"/api/v1/media/for-node/{item['id']}").json()
    assert media["filename"] == "Łódź 🎵 (card).png"

    thumbnail = client.get(media["thumbnail_url"])
    content = client.get(media["content_url"])

    assert thumbnail.status_code == 200
    assert content.status_code == 200
    assert "filename*=UTF-8''" in thumbnail.headers["content-disposition"]
    assert client.delete("/api/v1/example/tune/installation").status_code == 200


def test_a_failure_part_way_through_the_covers_leaves_no_media(
    client: TestClient, postgres_sync_url: str, media_dir: Path
) -> None:
    """The second cover fails; the first one's asset, row and files are removed."""

    class FailingSecond(CoverPackTarget):
        calls = 0

        async def create(self, item_id: uuid.UUID, name: str, style: str) -> Created:
            type(self).calls += 1
            if type(self).calls == 2:
                raise RuntimeError("cover boom")
            return await super().create(item_id, name, style)

    def failing(
        session_factory: Annotated[
            async_sessionmaker[AsyncSession], Depends(get_session_factory)
        ],
        storage: Annotated[MediaStoragePort, Depends(get_media_storage)],
    ) -> CoverPackTarget:
        return FailingSecond(
            build_cover_stores(session_factory),
            renderer=PillowCoverRenderer(),
            storage=storage,
            policy=ContentTypeAttachmentPolicy(),
            image_processor=PillowImageProcessor(),
        )

    app = cast("FastAPI", client.app)
    app.dependency_overrides[get_cover_pack_target] = failing

    with pytest.raises(InstallFailedError, match="Nothing was left behind"):
        client.put("/api/v1/example/demo/installation")

    assert _media_state(postgres_sync_url, media_dir) == (0, 0, 0)
    assert client.get("/api/v1/node?limit=100").json() == []
    assert client.get("/api/v1/node-type").json() == []


@pytest.fixture
def add_on_client(
    postgres_url: str, postgres_sync_url: str, tmp_path: Path
) -> Iterator[TestClient]:
    """Like `client`, over a small base pack and an add-on that needs it."""
    packs: dict[str, dict[str, Any]] = {
        "base": {
            "format": "menagerist-example-pack",
            "version": 4,
            "id": "base",
            "relationship_types": [
                {"ref": "by", "slug": "by", "label": "By", "reverse_label": "Made"}
            ],
            "item_types": [{"ref": "thing", "slug": "thing", "label": "Thing"}],
            "items": [{"ref": "a", "type": "thing", "name": "Base A"}],
        },
        "extra": {
            "format": "menagerist-example-pack",
            "version": 4,
            "id": "extra",
            "requires": ["base"],
            "items": [{"ref": "x", "type": "base:thing", "name": "Extra X"}],
            "connections": [{"from": "x", "to": "base:a", "type": "base:by"}],
            "collections": [{"ref": "mix", "name": "Mix", "items": ["x", "base:a"]}],
        },
    }
    index = {
        "format": "menagerist-examples-index",
        "version": 1,
        "packs": [
            {"id": "base", "name": "Base", "description": "The base."},
            {"id": "extra", "name": "Extra", "description": "Needs the base."},
        ],
    }
    for pack_id, data in packs.items():
        (tmp_path / f"{pack_id}.json").write_text(json.dumps(data), encoding="utf-8")
    (tmp_path / "index.json").write_text(json.dumps(index), encoding="utf-8")
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


def test_an_add_on_connects_to_its_base_and_blocks_its_removal(
    add_on_client: TestClient,
) -> None:
    """The add-on needs the base, links to its item, and is removed first."""
    c = add_on_client
    assert c.put("/api/v1/example/extra/installation").status_code == 409
    assert c.put("/api/v1/example/base/installation").status_code == 200

    added = c.put("/api/v1/example/extra/installation")

    assert added.status_code == 200, added.text
    assert added.json()["created"]["items"] == 1
    assert added.json()["created"]["connections"] == 1
    items = {n["name"]: n for n in c.get("/api/v1/node?limit=100").json()}
    assert set(items) == {"Base A", "Extra X"}
    (edge,) = c.get("/api/v1/edge?limit=100").json()
    assert (edge["source_id"], edge["target_id"]) == (
        items["Extra X"]["id"],
        items["Base A"]["id"],
    )
    assert len(c.get("/api/v1/collection").json()) == 1

    blocked = c.delete("/api/v1/example/base/installation")
    assert blocked.status_code == 409
    assert "Remove Extra first" in blocked.json()["detail"]
    assert len(c.get("/api/v1/node?limit=100").json()) == 2

    assert c.delete("/api/v1/example/extra/installation").status_code == 200
    assert [n["name"] for n in c.get("/api/v1/node?limit=100").json()] == ["Base A"]
    assert c.get("/api/v1/edge?limit=100").json() == []
    assert c.delete("/api/v1/example/base/installation").status_code == 200
    assert c.get("/api/v1/node?limit=100").json() == []


@pytest.fixture
def shipped_client(
    postgres_url: str, postgres_sync_url: str, media_dir: Path
) -> Iterator[TestClient]:
    """Like `client`, over the packs shipped with the app."""
    get_session_factory.cache_clear()
    get_engine.cache_clear()
    app = create_app()
    storage = LocalFilesystemMediaStorage(media_dir)
    app.dependency_overrides[get_media_storage] = lambda: storage
    try:
        with TestClient(app) as c:
            yield c
    finally:
        get_session_factory.cache_clear()
        get_engine.cache_clear()
        _wipe(postgres_sync_url)


def test_the_shipped_games_extras_add_on_end_to_end(
    shipped_client: TestClient, postgres_sync_url: str, media_dir: Path
) -> None:
    """Extra board games needs Board games, links to it, and leaves nothing behind."""
    c = shipped_client
    assert c.put("/api/v1/example/games-extras/installation").status_code == 409
    assert c.put("/api/v1/example/games/installation").status_code == 200

    added = c.put("/api/v1/example/games-extras/installation")

    assert added.status_code == 200, added.text
    assert added.json()["created"]["items"] == 5
    items = {n["name"]: n["id"] for n in c.get("/api/v1/node?limit=200").json()}
    edges = {
        (e["source_id"], e["target_id"]): e["type"]
        for e in c.get("/api/v1/edge?limit=200").json()
    }
    assert (
        edges[(items["Lantern Harbour: The Night Fair"], items["Lantern Harbour"])]
        == "games-expansion-of"
    )
    assert (
        edges[(items["Quillfeather Quarry"], items["Marrow Lane Press"])]
        == "games-published-by"
    )
    blocked = c.delete("/api/v1/example/games/installation")
    assert blocked.status_code == 409
    assert "Remove Extra board games first" in blocked.json()["detail"]

    assert c.delete("/api/v1/example/games-extras/installation").json()["kept"] == []
    assert c.delete("/api/v1/example/games/installation").json()["kept"] == []
    assert c.get("/api/v1/node?limit=200").json() == []
    assert c.get("/api/v1/edge?limit=200").json() == []
    assert _media_state(postgres_sync_url, media_dir) == (0, 0, 0)
