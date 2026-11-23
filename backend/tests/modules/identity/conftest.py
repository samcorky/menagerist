"""Shared fixtures: an all-in-memory identity world."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from app.modules.identity.adapters.persistence.in_memory_api_token_repository import (
    InMemoryApiTokenRepository,
)
from app.modules.identity.adapters.persistence.in_memory_device_repository import (
    InMemoryDeviceRepository,
)
from app.modules.identity.adapters.persistence.in_memory_session_repository import (
    InMemorySessionRepository,
)
from app.modules.identity.adapters.persistence.in_memory_sign_in_attempt_repository import (  # noqa: E501
    InMemorySignInAttemptRepository,
)
from app.modules.identity.adapters.persistence.in_memory_user_repository import (
    InMemoryUserRepository,
)
from app.modules.identity.adapters.security.in_memory_password_hasher import (
    InMemoryPasswordHasher,
)
from app.modules.identity.domain.user import Role, User
from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

if TYPE_CHECKING:
    from httpx2 import Response
    from starlette.testclient import TestClient

    from app.platform.config import IdentitySettings

AUTH = "/api/v1/auth"
FOREIGN_ORIGIN = "https://evil.example"
SETUP_BODY = {
    "username": "Admin",
    "display_name": "Admin",
    "password": "password-123",
}
NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


@dataclass(kw_only=True)
class World:
    """Everything an identity test needs, all in memory."""

    users: InMemoryUserRepository
    sessions: InMemorySessionRepository
    attempts: InMemorySignInAttemptRepository
    tokens: InMemoryApiTokenRepository
    devices: InMemoryDeviceRepository
    uow: InMemoryUnitOfWork[IdentityRepos]

    def build_api(
        self,
        *,
        base_url: str = "http://testserver",
        settings: IdentitySettings | None = None,
    ) -> IdentityApi:
        """Build the real app over this world; tests reach it through `api`."""
        return IdentityApi(self, base_url=base_url, settings=settings)


MakeUser = Callable[..., User]


@pytest.fixture
def world() -> World:
    """Return a fresh in-memory world."""
    users = InMemoryUserRepository()
    sessions = InMemorySessionRepository()
    attempts = InMemorySignInAttemptRepository()
    tokens = InMemoryApiTokenRepository()
    devices = InMemoryDeviceRepository()
    return World(
        users=users,
        sessions=sessions,
        attempts=attempts,
        tokens=tokens,
        devices=devices,
        uow=InMemoryUnitOfWork(
            IdentityRepos(
                users=users,
                sessions=sessions,
                attempts=attempts,
                tokens=tokens,
                devices=devices,
            )
        ),
    )


@pytest.fixture
def make_user() -> MakeUser:
    """Return a factory building a user whose password is `password-123`."""

    def _make(
        username: str = "alice",
        *,
        display_name: str | None = None,
        role: Role = Role.MEMBER,
        password: str = "password-123",
    ) -> User:
        return User.create(
            username=username,
            display_name=display_name or username.title(),
            password_hash=InMemoryPasswordHasher().hash(password),
            role=role,
            now=NOW,
        )

    return _make


class IdentityApi:
    """The real app over the in-memory identity world, with same-origin helpers.

    The app and its dependencies are imported when one is built, so the domain and
    application tests that share this file do not pay for importing the API.
    """

    def __init__(
        self,
        world: World,
        *,
        base_url: str = "http://testserver",
        settings: IdentitySettings | None = None,
    ) -> None:
        from app.entrypoints.api import create_app
        from app.modules.identity.adapters.api.dependencies import (
            get_decoy_hash,
            get_existing_data_claim,
            get_identity_repos,
            get_identity_settings_dep,
            get_identity_uow,
            get_password_hasher,
            get_setup_identity_uow,
        )
        from app.modules.identity.adapters.claim.no_op_existing_data_claim import (
            NoOpExistingDataClaim,
        )

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
        self.app.dependency_overrides[get_identity_uow] = lambda: world.uow
        self.app.dependency_overrides[get_setup_identity_uow] = lambda: world.uow
        self.app.dependency_overrides[get_existing_data_claim] = NoOpExistingDataClaim
        self.app.dependency_overrides[get_identity_repos] = lambda: repos
        self.app.dependency_overrides[get_password_hasher] = lambda: hasher
        self.app.dependency_overrides[get_decoy_hash] = lambda: hasher.hash("decoy")
        if settings is not None:
            self.app.dependency_overrides[get_identity_settings_dep] = lambda: settings
        self.client = self.new_client(base_url)

    def new_client(self, base_url: str = "http://testserver") -> TestClient:
        """Return a client with no cookies that sends its own `Origin`."""
        from starlette.testclient import TestClient

        client = TestClient(self.app, base_url=base_url)
        client.cookies.clear()
        return client

    @staticmethod
    def post(
        client: TestClient,
        url: str,
        json: Mapping[str, object] | None = None,
        *,
        csrf: bool = True,
    ) -> Response:
        """POST from the client's own origin; a foreign one if `csrf` is off."""
        headers = {} if csrf else {"Origin": FOREIGN_ORIGIN}
        return client.post(url, json=json, headers=headers)

    @staticmethod
    def patch(client: TestClient, url: str, json: Mapping[str, object]) -> Response:
        """PATCH from the client's own origin."""
        return client.patch(url, json=json)

    @staticmethod
    def delete(client: TestClient, url: str, *, csrf: bool = True) -> Response:
        """DELETE from the client's own origin; a foreign one if `csrf` is off."""
        headers = {} if csrf else {"Origin": FOREIGN_ORIGIN}
        return client.delete(url, headers=headers)

    def setup(self, client: TestClient | None = None) -> Response:
        """Run first-run setup, leaving `client` signed in as an admin."""
        response = self.post(client or self.client, f"{AUTH}/setup", SETUP_BODY)
        assert response.status_code == 201
        return response

    async def add_user(
        self, make_user: MakeUser, username: str, role: Role = Role.MEMBER
    ) -> None:
        """Store a user whose password is `password-123`."""
        await self.world.users.add(make_user(username, role=role))

    def sign_in(
        self,
        username: str = "alice",
        password: str = "password-123",
        *,
        headers: Mapping[str, str] | None = None,
    ) -> tuple[TestClient, Response]:
        """Sign in with a fresh client, returning it and the response."""
        client = self.new_client()
        response = client.post(
            f"{AUTH}/login",
            json={"username": username, "password": password},
            headers=dict(headers or {}),
        )
        return client, response


@pytest.fixture
def api(world: World) -> IdentityApi:
    """An app wired to the in-memory identity world."""
    return world.build_api()
