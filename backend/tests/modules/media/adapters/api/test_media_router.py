import uuid
from typing import TYPE_CHECKING

from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.modules.media.adapters.api.dependencies import (
    get_image_processor,
    get_media_repos,
    get_media_storage,
    get_media_uow,
)
from app.modules.media.adapters.imaging.in_memory_image_processor import (
    InMemoryImageProcessor,
)
from app.modules.media.adapters.persistence.in_memory_media_asset_repository import (
    InMemoryMediaAssetRepository,
)
from app.modules.media.adapters.persistence.unit_of_work import (
    create_in_memory_media_uow,
    make_in_memory_repos,
)
from app.modules.media.adapters.storage.in_memory_media_storage import (
    InMemoryMediaStorage,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

TINY_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010101004800480000ffdb004300080606070605080707070909080a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c1c28372930313434341f27393d38323c2e333432ffc0000b080001000101011100ffc4001f0000010501010101010100000000000000000102030405060708090a0bffda0008010100003f00bf00ffd9"
)


def _app_with_in_memory_media() -> tuple[
    FastAPI, InMemoryMediaAssetRepository, InMemoryMediaStorage
]:
    app = create_app()
    repo = InMemoryMediaAssetRepository()
    storage = InMemoryMediaStorage()
    image_processor = InMemoryImageProcessor()
    repos = make_in_memory_repos(assets=repo)
    uow = create_in_memory_media_uow(repos)
    app.dependency_overrides[get_media_uow] = lambda: uow
    app.dependency_overrides[get_media_repos] = lambda: repos
    app.dependency_overrides[get_media_storage] = lambda: storage
    app.dependency_overrides[get_image_processor] = lambda: image_processor
    return app, repo, storage


def test_stage_and_get_round_trip() -> None:
    """POST /media stages an asset; GET /media/{id} returns its metadata."""
    app, _, _ = _app_with_in_memory_media()
    client = TestClient(app)

    response = client.post(
        "/api/v1/media",
        files={"file": ("cover.jpg", TINY_JPEG, "image/jpeg")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "staged"
    assert body["filename"] == "cover.jpg"
    assert body["content_type"] == "image/jpeg"
    assert body["size"] == len(TINY_JPEG)
    assert body["thumbnail_url"] == f"/api/v1/media/{body['id']}/thumbnail"

    get_response = client.get(f"/api/v1/media/{body['id']}")
    assert get_response.status_code == 200
    assert get_response.json() == body


def test_get_media_returns_404_for_missing_id() -> None:
    """GET /media/{id} returns 404 for an unknown id."""
    app, _, _ = _app_with_in_memory_media()
    client = TestClient(app)

    response = client.get(f"/api/v1/media/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["title"] == "MediaAssetNotFoundError"


def test_promote_transitions_to_attached() -> None:
    """POST /media/{id}/promote changes status to attached."""
    app, _, _ = _app_with_in_memory_media()
    client = TestClient(app)

    stage = client.post(
        "/api/v1/media",
        files={"file": ("f.jpg", b"data", "image/jpeg")},
    ).json()

    response = client.post(f"/api/v1/media/{stage['id']}/promote")

    assert response.status_code == 200
    assert response.json()["status"] == "attached"


def test_promote_returns_404_for_missing_asset() -> None:
    """POST /media/{id}/promote returns 404 for an unknown id."""
    app, _, _ = _app_with_in_memory_media()
    client = TestClient(app)

    response = client.post(f"/api/v1/media/{uuid.uuid4()}/promote")

    assert response.status_code == 404


def test_update_media_renames_filename_without_changing_extension() -> None:
    """PATCH /media/{id} updates the stored filename while keeping the extension."""
    app, _, _ = _app_with_in_memory_media()
    client = TestClient(app)

    stage = client.post(
        "/api/v1/media",
        files={"file": ("cover.jpg", b"data", "image/jpeg")},
    ).json()

    response = client.patch(
        f"/api/v1/media/{stage['id']}",
        json={"filename": "front page"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["filename"] == "front page.jpg"

    get_response = client.get(f"/api/v1/media/{stage['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["filename"] == "front page.jpg"


def test_update_media_rejects_extension_change() -> None:
    """PATCH /media/{id} rejects attempts to replace the file extension."""
    app, _, _ = _app_with_in_memory_media()
    client = TestClient(app)

    stage = client.post(
        "/api/v1/media",
        files={"file": ("cover.jpg", b"data", "image/jpeg")},
    ).json()

    response = client.patch(
        f"/api/v1/media/{stage['id']}",
        json={"filename": "front.png"},
    )

    assert response.status_code == 400
    assert "filename extension cannot be changed" in response.text


def test_orphan_transitions_to_orphaned() -> None:
    """POST /media/{id}/orphan changes status from attached to orphaned."""
    app, _, _ = _app_with_in_memory_media()
    client = TestClient(app)

    stage = client.post(
        "/api/v1/media",
        files={"file": ("f.jpg", b"data", "image/jpeg")},
    ).json()
    client.post(f"/api/v1/media/{stage['id']}/promote")

    response = client.post(f"/api/v1/media/{stage['id']}/orphan")

    assert response.status_code == 200
    assert response.json()["status"] == "orphaned"


def test_orphan_returns_400_if_not_attached() -> None:
    """POST /media/{id}/orphan returns 400 when asset is staged."""
    app, _, _ = _app_with_in_memory_media()
    client = TestClient(app)

    stage = client.post(
        "/api/v1/media",
        files={"file": ("f.jpg", b"data", "image/jpeg")},
    ).json()

    response = client.post(f"/api/v1/media/{stage['id']}/orphan")

    assert response.status_code == 400


def test_delete_removes_asset() -> None:
    """DELETE /media/{id} returns 204 and the asset is no longer retrievable."""
    app, _, _ = _app_with_in_memory_media()
    client = TestClient(app)

    stage = client.post(
        "/api/v1/media",
        files={"file": ("f.jpg", b"data", "image/jpeg")},
    ).json()

    delete_response = client.delete(f"/api/v1/media/{stage['id']}")
    assert delete_response.status_code == 204

    assert client.get(f"/api/v1/media/{stage['id']}").status_code == 404


def test_delete_returns_404_for_missing_asset() -> None:
    """DELETE /media/{id} returns 404 for an unknown id."""
    app, _, _ = _app_with_in_memory_media()
    client = TestClient(app)

    response = client.delete(f"/api/v1/media/{uuid.uuid4()}")

    assert response.status_code == 404


def test_stream_content_returns_bytes() -> None:
    """GET /media/{id}/content streams the file bytes with caching headers."""
    app, _, _ = _app_with_in_memory_media()
    client = TestClient(app)

    stage = client.post(
        "/api/v1/media",
        files={"file": ("f.jpg", TINY_JPEG, "image/jpeg")},
    ).json()

    response = client.get(f"/api/v1/media/{stage['id']}/content")

    assert response.status_code == 200
    assert response.content == TINY_JPEG
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["content-disposition"] == 'inline; filename="f.jpg"'
    assert "etag" in response.headers
    assert "cache-control" in response.headers

    # Conditional GET via ETag
    etag = response.headers["etag"]
    cached_resp = client.get(
        f"/api/v1/media/{stage['id']}/content",
        headers={"If-None-Match": etag},
    )
    assert cached_resp.status_code == 304


def test_stream_thumbnail_returns_thumbnail_bytes() -> None:
    """GET /media/{id}/thumbnail streams the thumbnail bytes."""
    app, _, _ = _app_with_in_memory_media()
    client = TestClient(app)

    stage = client.post(
        "/api/v1/media",
        files={"file": ("f.jpg", TINY_JPEG, "image/jpeg")},
    ).json()

    response = client.get(f"/api/v1/media/{stage['id']}/thumbnail")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert response.headers["content-disposition"] == 'inline; filename="f.jpg.webp"'
    assert "etag" in response.headers

    # Conditional GET via ETag
    etag = response.headers["etag"]
    cached_resp = client.get(
        f"/api/v1/media/{stage['id']}/thumbnail",
        headers={"If-None-Match": etag},
    )
    assert cached_resp.status_code == 304


def test_stream_thumbnail_returns_404_when_no_thumbnail() -> None:
    """GET /media/{id}/thumbnail returns 404 when asset has no thumbnail."""
    app, _, _ = _app_with_in_memory_media()
    client = TestClient(app)

    stage = client.post(
        "/api/v1/media",
        files={"file": ("doc.txt", b"plain text", "text/plain")},
    ).json()

    response = client.get(f"/api/v1/media/{stage['id']}/thumbnail")
    assert response.status_code == 404
