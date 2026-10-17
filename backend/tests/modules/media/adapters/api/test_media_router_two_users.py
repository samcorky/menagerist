"""Media routes with two signed-in people: nothing leaks across."""

import uuid
from typing import TYPE_CHECKING

import pytest
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.bridges.attach_target_access import (
    get_attach_target_access,
)
from app.modules.media.adapters.api.dependencies import (
    get_image_processor,
    get_media_repos,
    get_media_storage,
    get_media_uow,
)
from app.modules.media.adapters.imaging.in_memory_image_processor import (
    InMemoryImageProcessor,
)
from app.modules.media.adapters.persistence.in_memory_attach_target_access import (
    InMemoryAttachTargetAccess,
)
from app.modules.media.adapters.persistence.unit_of_work import (
    create_in_memory_media_uow,
    make_in_memory_repos,
)
from app.modules.media.adapters.storage.in_memory_media_storage import (
    InMemoryMediaStorage,
)
from app.modules.media.domain.media_attachment import AttachmentTarget

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI

ALICE = uuid.UUID(int=101)
BOB = uuid.UUID(int=102)
BASE = "/api/v1/media"
TINY_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010101004800480000ffdb004300080606070605080707070909080a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c1c28372930313434341f27393d38323c2e333432ffc0000b080001000101011100ffc4001f0000010501010101010100000000000000000102030405060708090a0bffda0008010100003f00bf00ffd9"
)
JPEG = ("c.jpg", TINY_JPEG, "image/jpeg")


class _World:
    def __init__(self, as_user: Callable[..., None]) -> None:
        self.app: FastAPI = create_app()
        self.repos = make_in_memory_repos()
        self.uow = create_in_memory_media_uow(self.repos)
        self.storage = InMemoryMediaStorage()
        self.targets = InMemoryAttachTargetAccess()
        processor = InMemoryImageProcessor()
        overrides = self.app.dependency_overrides
        overrides[get_media_uow] = lambda: self.uow
        overrides[get_media_repos] = lambda: self.repos
        overrides[get_media_storage] = lambda: self.storage
        overrides[get_image_processor] = lambda: processor
        overrides[get_attach_target_access] = lambda: self.targets
        self._as_user = as_user
        self.client = TestClient(self.app)

    def act_as(self, user_id: uuid.UUID) -> TestClient:
        self._as_user(self.app, user_id)
        return self.client

    def item(self, owner: uuid.UUID) -> uuid.UUID:
        item_id = uuid.uuid7()
        self.targets.add_target(AttachmentTarget.NODE, item_id, owner)
        return item_id


@pytest.fixture
def world(as_user: Callable[..., None]) -> _World:
    """A fresh app over in-memory media."""
    return _World(as_user)


def _stage(client: TestClient) -> str:
    response = client.post(BASE, files={"file": JPEG})
    assert response.status_code == 201
    return str(response.json()["id"])


def _attach(client: TestClient, asset_id: str, item: uuid.UUID) -> object:
    return client.post(
        f"{BASE}/{asset_id}/attachments",
        json={"target_type": "node", "target_id": str(item)},
    )


def test_other_user_gets_404_on_every_asset_route(world: _World) -> None:
    """B cannot read, change, stream or delete A's asset."""
    item = world.item(ALICE)
    alice = world.act_as(ALICE)
    asset_id = _stage(alice)
    assert _attach(alice, asset_id, item).status_code == 201  # type: ignore[attr-defined]
    url = f"{BASE}/{asset_id}"
    body = {"target_type": "node", "target_id": str(item)}
    bob = world.act_as(BOB)

    assert bob.get(url).status_code == 404
    assert bob.get(f"{url}/content").status_code == 404
    assert bob.get(f"{url}/thumbnail").status_code == 404
    assert bob.patch(url, json={"filename": "mine"}).status_code == 404
    assert bob.post(f"{url}/promote").status_code == 404
    assert bob.post(f"{url}/orphan").status_code == 404
    assert bob.request("DELETE", f"{url}/attachments", json=body).status_code == 404
    assert bob.post(f"{url}/attachments/cover", json=body).status_code == 404
    assert (
        bob.request("DELETE", f"{url}/attachments/cover", json=body).status_code == 404
    )
    assert bob.delete(url).status_code == 404
    assert world.act_as(ALICE).get(url).status_code == 200
    assert world.act_as(ALICE).get(f"{url}/content").content == TINY_JPEG


def test_foreign_asset_is_404_before_any_304(world: _World) -> None:
    """A matching validator never reveals another person's file."""
    alice = world.act_as(ALICE)
    asset_id = _stage(alice)
    url = f"{BASE}/{asset_id}"
    own = alice.get(f"{url}/content")
    etag = own.headers["ETag"]
    thumb_etag = alice.get(f"{url}/thumbnail").headers["ETag"]
    bob = world.act_as(BOB)

    content = bob.get(f"{url}/content", headers={"If-None-Match": etag})
    thumbnail = bob.get(f"{url}/thumbnail", headers={"If-None-Match": thumb_etag})

    assert content.status_code == 404
    assert thumbnail.status_code == 404
    assert (
        world.act_as(ALICE)
        .get(f"{url}/content", headers={"If-None-Match": etag})
        .status_code
        == 304
    )


def test_content_responses_are_private_for_the_owner(world: _World) -> None:
    """Per-user authorisation applies, so shared caches must not keep the bytes."""
    alice = world.act_as(ALICE)
    asset_id = _stage(alice)
    url = f"{BASE}/{asset_id}"

    for path in ("content", "thumbnail"):
        response = alice.get(f"{url}/{path}")
        assert response.headers["Cache-Control"] == "private, no-cache"
        revalidated = alice.get(
            f"{url}/{path}", headers={"If-None-Match": response.headers["ETag"]}
        )
        assert revalidated.status_code == 304
        assert revalidated.headers["Cache-Control"] == "private, no-cache"


def test_other_user_cannot_attach_a_foreign_asset(world: _World) -> None:
    """B cannot attach A's asset, even to B's own item."""
    asset_id = _stage(world.act_as(ALICE))
    bobs_item = world.item(BOB)

    response = _attach(world.act_as(BOB), asset_id, bobs_item)

    assert response.status_code == 404  # type: ignore[attr-defined]
    assert world.act_as(ALICE).get(f"{BASE}/{asset_id}").json()["status"] == "staged"


def test_cannot_attach_to_another_users_item(world: _World) -> None:
    """B cannot attach B's own asset to A's item; nothing changes."""
    alices_item = world.item(ALICE)
    bob = world.act_as(BOB)
    asset_id = _stage(bob)

    response = _attach(bob, asset_id, alices_item)

    assert response.status_code == 404  # type: ignore[attr-defined]
    assert bob.get(f"{BASE}/{asset_id}").json()["status"] == "staged"
    assert world.act_as(ALICE).get(f"{BASE}/for-node/{alices_item}").json() == []


def test_cannot_upload_and_attach_to_another_users_item(world: _World) -> None:
    """The one-shot upload is refused for a foreign item and stores nothing."""
    alices_item = world.item(ALICE)
    bob = world.act_as(BOB)

    response = bob.post(
        f"{BASE}/attached",
        data={"target_type": "node", "target_id": str(alices_item)},
        files={"file": JPEG},
    )

    assert response.status_code == 404
    assert world.storage._files == {}
    assert world.repos.assets._assets == {}  # type: ignore[attr-defined]


def test_listing_media_for_another_users_item_is_empty(world: _World) -> None:
    """B sees nothing on A's item; A sees the file."""
    item = world.item(ALICE)
    alice = world.act_as(ALICE)
    assert _attach(alice, _stage(alice), item).status_code == 201  # type: ignore[attr-defined]

    assert len(alice.get(f"{BASE}/for-node/{item}").json()) == 1
    assert world.act_as(BOB).get(f"{BASE}/for-node/{item}").json() == []


def test_uploads_are_owned_by_the_uploader(world: _World) -> None:
    """Each person's staged file is visible to them alone."""
    asset_id = _stage(world.act_as(ALICE))

    assert world.act_as(ALICE).get(f"{BASE}/{asset_id}").status_code == 200
    assert world.act_as(BOB).get(f"{BASE}/{asset_id}").status_code == 404
