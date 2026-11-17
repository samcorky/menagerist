"""Router tests for the picture routes under /api/v1/me and /api/v1/users."""

from typing import TYPE_CHECKING

import pytest
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.modules.identity.adapters.api.dependencies import (
    get_avatar_image_processor,
    get_avatar_storage,
    get_cat_picture_source,
    get_identity_repos,
    get_identity_uow,
    get_password_hasher,
)
from app.modules.identity.adapters.cats.in_memory_cat_picture_source import (
    InMemoryCatPictureSource,
)
from app.modules.identity.adapters.imaging.in_memory_avatar_processor import (
    InMemoryAvatarProcessor,
)
from app.modules.identity.adapters.security.in_memory_password_hasher import (
    InMemoryPasswordHasher,
)
from app.modules.identity.adapters.storage.in_memory_avatar_storage import (
    InMemoryAvatarStorage,
)
from app.modules.identity.domain.avatar import MAX_AVATAR_BYTES
from app.modules.identity.domain.user import Role
from app.modules.identity.ports.unit_of_work import IdentityRepos

if TYPE_CHECKING:
    from tests.modules.identity.conftest import MakeUser, World

ME = "/api/v1/me"
USERS = "/api/v1/users"
AVATAR = f"{ME}/avatar"
PNG = ("me.png", b"fake png bytes", "image/png")


class PictureApi:
    """The app over the in-memory identity world, with in-memory picture adapters."""

    def __init__(self, world: World, cats: list[bytes] | None = None) -> None:
        self.world = world
        self.app = create_app()
        hasher = InMemoryPasswordHasher()
        repos = IdentityRepos(
            users=world.users,
            sessions=world.sessions,
            attempts=world.attempts,
            tokens=world.tokens,
            devices=world.devices,
        )
        self.storage = InMemoryAvatarStorage()
        self.processor = InMemoryAvatarProcessor()
        self.cats = InMemoryCatPictureSource(cats or [])
        overrides = self.app.dependency_overrides
        overrides[get_identity_uow] = lambda: world.uow
        overrides[get_identity_repos] = lambda: repos
        overrides[get_password_hasher] = lambda: hasher
        overrides[get_avatar_storage] = lambda: self.storage
        overrides[get_avatar_image_processor] = lambda: self.processor
        overrides[get_cat_picture_source] = lambda: self.cats

    def new_client(self) -> TestClient:
        """Return a client with no cookies."""
        client = TestClient(self.app, base_url="http://testserver")
        client.cookies.clear()
        return client

    async def add_user(
        self, make_user: MakeUser, username: str, role: Role = Role.MEMBER
    ) -> None:
        """Store a user whose password is `password-123`."""
        await self.world.users.add(make_user(username, role=role))

    def sign_in(self, username: str) -> tuple[TestClient, object]:
        """Sign in with a fresh client."""
        client = self.new_client()
        response = client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": "password-123"},
        )
        return client, response


@pytest.fixture
async def signed_in(world: World, make_user: MakeUser) -> tuple[PictureApi, TestClient]:
    """The app with Alice signed in and one cat queued."""
    api = PictureApi(world, cats=[b"meow"])
    await api.add_user(make_user, "alice")
    client, response = api.sign_in("alice")
    assert getattr(response, "status_code", None) == 200
    return api, client


def test_put_avatar_returns_version(signed_in: tuple[PictureApi, TestClient]) -> None:
    """An upload answers with the account, now carrying its picture's version."""
    _api, client = signed_in
    response = client.put(AVATAR, files={"file": PNG})
    assert response.status_code == 200
    body = response.json()
    assert len(body["avatar_version"]) == 16
    assert body["avatar_source"] == "upload"
    assert client.get(ME).json()["avatar_version"] == body["avatar_version"]


def test_put_drawn_and_crop(signed_in: tuple[PictureApi, TestClient]) -> None:
    """A drawn cat is recorded as drawn, and a full crop reaches the processor."""
    api, client = signed_in
    response = client.put(
        AVATAR,
        files={"file": PNG},
        data={"source": "drawn", "crop_x": "1", "crop_y": "2", "crop_size": "3"},
    )
    assert response.status_code == 200
    assert response.json()["avatar_source"] == "drawn"
    (crop,) = api.processor.crops
    assert crop is not None
    assert (crop.x, crop.y, crop.size) == (1, 2, 3)


def test_put_with_partial_crop_is_400(signed_in: tuple[PictureApi, TestClient]) -> None:
    """A crop needs all three numbers or none."""
    _api, client = signed_in
    response = client.put(
        AVATAR, files={"file": PNG}, data={"crop_x": "1", "crop_size": "3"}
    )
    assert response.status_code == 400


def test_put_with_negative_crop_is_400(
    signed_in: tuple[PictureApi, TestClient],
) -> None:
    """A crop starting outside the picture is refused."""
    _api, client = signed_in
    response = client.put(
        AVATAR,
        files={"file": PNG},
        data={"crop_x": "-1", "crop_y": "0", "crop_size": "3"},
    )
    assert response.status_code == 400


def test_put_cat_source_is_rejected(signed_in: tuple[PictureApi, TestClient]) -> None:
    """An upload cannot claim to be a cat from the service."""
    _api, client = signed_in
    response = client.put(AVATAR, files={"file": PNG}, data={"source": "cat"})
    assert response.status_code in {400, 422}


def test_put_too_large_is_400(signed_in: tuple[PictureApi, TestClient]) -> None:
    """A file over 5 MB is refused without being decoded."""
    api, client = signed_in
    big = ("big.png", b"x" * (MAX_AVATAR_BYTES + 1), "image/png")
    response = client.put(AVATAR, files={"file": big})
    assert response.status_code in {400, 413}
    assert api.processor.crops == []


def test_put_unusable_file_is_400(signed_in: tuple[PictureApi, TestClient]) -> None:
    """A file the processor cannot use answers 400 with a problem body."""
    api, client = signed_in
    api.processor.fail_next = True
    response = client.put(AVATAR, files={"file": PNG})
    assert response.status_code == 400
    assert response.json()["title"] == "InvalidAvatarError"


def test_post_cat_returns_cat_source(signed_in: tuple[PictureApi, TestClient]) -> None:
    """Random cat answers with the account showing a cat."""
    _api, client = signed_in
    response = client.post(f"{AVATAR}/cat")
    assert response.status_code == 200
    assert response.json()["avatar_source"] == "cat"


def test_post_cat_unavailable_is_503_problem(
    signed_in: tuple[PictureApi, TestClient],
) -> None:
    """When the service gives nothing, the browser is told so it can draw one."""
    _api, client = signed_in
    assert client.post(f"{AVATAR}/cat").status_code == 200
    response = client.post(f"{AVATAR}/cat")
    assert response.status_code == 503
    assert response.json()["title"] == "CatServiceUnavailableError"


def test_cat_press_is_rate_limited(
    monkeypatch: pytest.MonkeyPatch, signed_in: tuple[PictureApi, TestClient]
) -> None:
    """Each press is an outbound fetch, so presses share the upload allowance."""
    monkeypatch.setenv("MENAGERIST_RATE_LIMIT_UPLOADS_PER_MINUTE", "1")
    _api, client = signed_in
    client.post(f"{AVATAR}/cat")
    refused = client.post(f"{AVATAR}/cat")
    assert refused.status_code == 429


def test_delete_own_clears(signed_in: tuple[PictureApi, TestClient]) -> None:
    """Use initials removes the picture and its files."""
    api, client = signed_in
    client.put(AVATAR, files={"file": PNG})
    response = client.delete(AVATAR)
    assert response.status_code == 200
    assert response.json()["avatar_version"] is None
    assert api.storage.files == {}


async def test_admin_delete_other_clears(world: World, make_user: MakeUser) -> None:
    """An administrator can remove someone's picture."""
    api = PictureApi(world)
    await api.add_user(make_user, "alice")
    await api.add_user(make_user, "root", Role.ADMIN)
    alice, _ = api.sign_in("alice")
    user_id = alice.put(AVATAR, files={"file": PNG}).json()["id"]
    admin, _ = api.sign_in("root")

    response = admin.delete(f"{USERS}/{user_id}/avatar")

    assert response.status_code == 200
    assert response.json()["avatar_version"] is None


async def test_member_delete_other_is_403(world: World, make_user: MakeUser) -> None:
    """Members cannot remove other people's pictures."""
    api = PictureApi(world)
    await api.add_user(make_user, "alice")
    await api.add_user(make_user, "bob")
    alice, _ = api.sign_in("alice")
    user_id = alice.put(AVATAR, files={"file": PNG}).json()["id"]
    bob, _ = api.sign_in("bob")
    assert bob.delete(f"{USERS}/{user_id}/avatar").status_code == 403


async def test_get_avatar_bytes_and_cache_headers(
    world: World, make_user: MakeUser
) -> None:
    """Another member loads the picture, cacheable for a year at that address."""
    api = PictureApi(world)
    await api.add_user(make_user, "alice")
    await api.add_user(make_user, "bob")
    alice, _ = api.sign_in("alice")
    body = alice.put(AVATAR, files={"file": PNG}).json()
    bob, _ = api.sign_in("bob")

    response = bob.get(f"{USERS}/{body['id']}/avatar/128?v={body['avatar_version']}")

    assert response.status_code == 200
    assert response.content == f"{body['avatar_version']}-128".encode()
    assert response.headers["content-type"] == "image/webp"
    assert response.headers["cache-control"] == "private, max-age=31536000, immutable"
    assert response.headers["etag"] == f'"{body["avatar_version"]}-128"'
    assert response.headers["x-content-type-options"] == "nosniff"


def test_get_with_matching_etag_is_304(
    signed_in: tuple[PictureApi, TestClient],
) -> None:
    """A browser revalidating its copy gets a 304 with no body."""
    _api, client = signed_in
    body = client.put(AVATAR, files={"file": PNG}).json()
    url = f"{USERS}/{body['id']}/avatar/64?v={body['avatar_version']}"
    etag = client.get(url).headers["etag"]
    response = client.get(url, headers={"If-None-Match": etag})
    assert response.status_code == 304
    assert response.content == b""


def test_stale_version_is_404(signed_in: tuple[PictureApi, TestClient]) -> None:
    """The old address stops working once the picture changes."""
    _api, client = signed_in
    first = client.put(AVATAR, files={"file": PNG}).json()
    client.put(AVATAR, files={"file": ("b.png", b"other", "image/png")})
    url = f"{USERS}/{first['id']}/avatar/64?v={first['avatar_version']}"
    assert client.get(url).status_code == 404


def test_cleared_avatar_is_404(signed_in: tuple[PictureApi, TestClient]) -> None:
    """After Use initials, the picture's address is gone."""
    _api, client = signed_in
    body = client.put(AVATAR, files={"file": PNG}).json()
    client.delete(AVATAR)
    url = f"{USERS}/{body['id']}/avatar/64?v={body['avatar_version']}"
    assert client.get(url).status_code == 404


def test_get_requires_version_and_known_size(
    signed_in: tuple[PictureApi, TestClient],
) -> None:
    """The version is required, and only stored sizes exist."""
    _api, client = signed_in
    body = client.put(AVATAR, files={"file": PNG}).json()
    base = f"{USERS}/{body['id']}/avatar"
    assert client.get(f"{base}/64").status_code == 422
    assert client.get(f"{base}/99?v={body['avatar_version']}").status_code in {404, 422}


def test_get_requires_sign_in(signed_in: tuple[PictureApi, TestClient]) -> None:
    """Someone not signed in cannot load pictures."""
    api, client = signed_in
    body = client.put(AVATAR, files={"file": PNG}).json()
    anonymous = api.new_client()
    url = f"{USERS}/{body['id']}/avatar/64?v={body['avatar_version']}"
    assert anonymous.get(url).status_code == 401


def test_me_includes_avatar_fields(signed_in: tuple[PictureApi, TestClient]) -> None:
    """The account starts with no picture."""
    _api, client = signed_in
    me = client.get(ME).json()
    assert me["avatar_version"] is None
    assert me["avatar_source"] is None
