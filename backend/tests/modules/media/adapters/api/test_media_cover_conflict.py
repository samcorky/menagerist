"""A second cover on one item is a 409 problem response, not a server error."""

import uuid

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
from app.modules.media.adapters.persistence.unit_of_work import (
    create_in_memory_media_uow,
    make_in_memory_repos,
)
from app.modules.media.adapters.storage.in_memory_media_storage import (
    InMemoryMediaStorage,
)
from app.modules.media.domain.errors import COVER_ALREADY_SET_MESSAGE

TINY_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010101004800480000ffdb004300080606070605080707070909080a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c1c28372930313434341f27393d38323c2e333432ffc0000b080001000101011100ffc4001f0000010501010101010100000000000000000102030405060708090a0bffda0008010100003f00bf00ffd9"
)


def _client() -> TestClient:
    app = create_app()
    repos = make_in_memory_repos()
    uow = create_in_memory_media_uow(repos)
    app.dependency_overrides[get_media_uow] = lambda: uow
    app.dependency_overrides[get_media_repos] = lambda: repos
    storage = InMemoryMediaStorage()
    app.dependency_overrides[get_media_storage] = lambda: storage
    app.dependency_overrides[get_image_processor] = lambda: InMemoryImageProcessor()
    return TestClient(app)


def _stage(client: TestClient) -> str:
    response = client.post(
        "/api/v1/media", files={"file": ("c.jpg", TINY_JPEG, "image/jpeg")}
    )
    return str(response.json()["id"])


def _attach_cover(client: TestClient, asset_id: str, item_id: uuid.UUID) -> object:
    return client.post(
        f"/api/v1/media/{asset_id}/attachments",
        json={
            "target_type": "node",
            "target_id": str(item_id),
            "attribute_key": "cover",
        },
    )


def test_attach_second_cover_is_409_problem_json() -> None:
    """POST /media/{id}/attachments with a second cover returns a 409 problem."""
    client = _client()
    item_id = uuid.uuid4()
    assert _attach_cover(client, _stage(client), item_id).status_code == 201  # type: ignore[attr-defined]

    response = _attach_cover(client, _stage(client), item_id)

    assert response.status_code == 409  # type: ignore[attr-defined]
    assert response.headers["content-type"].startswith(  # type: ignore[attr-defined]
        "application/problem+json"
    )
    body = response.json()  # type: ignore[attr-defined]
    assert body["status"] == 409
    assert body["title"] == "CoverAlreadySetError"
    assert body["detail"] == COVER_ALREADY_SET_MESSAGE


def test_upload_and_attach_second_cover_is_409_problem_json() -> None:
    """POST /media/attached with a second cover returns the same 409 problem."""
    client = _client()
    item_id = uuid.uuid4()
    data = {"target_type": "node", "target_id": str(item_id), "attribute_key": "cover"}
    files = {"file": ("c.jpg", TINY_JPEG, "image/jpeg")}
    assert (
        client.post("/api/v1/media/attached", data=data, files=files).status_code == 201
    )

    response = client.post("/api/v1/media/attached", data=data, files=files)

    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["detail"] == COVER_ALREADY_SET_MESSAGE


def test_set_cover_endpoint_still_replaces_the_cover() -> None:
    """POST /media/{id}/attachments/cover moves the cover instead of conflicting."""
    client = _client()
    item_id = uuid.uuid4()
    first, second = _stage(client), _stage(client)
    assert _attach_cover(client, first, item_id).status_code == 201  # type: ignore[attr-defined]
    plain = client.post(
        f"/api/v1/media/{second}/attachments",
        json={"target_type": "node", "target_id": str(item_id)},
    )
    assert plain.status_code == 201

    response = client.post(
        f"/api/v1/media/{second}/attachments/cover",
        json={"target_type": "node", "target_id": str(item_id)},
    )

    assert response.status_code == 200
    assert response.json()["attribute_key"] == "cover"
