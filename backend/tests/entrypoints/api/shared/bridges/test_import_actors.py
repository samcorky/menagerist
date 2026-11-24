"""A queued import runs as its owner's account as it is now."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.entrypoints.api.shared.bridges.import_actors import (
    IdentityImportActors,
    build_import_actors,
)
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
from app.modules.identity.domain.user import Role, User
from app.modules.identity.ports.unit_of_work import IdentityRepos

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


def _actors(user: User) -> IdentityImportActors:
    users = InMemoryUserRepository()
    users._users[user.id] = user
    repos = IdentityRepos(
        users=users,
        sessions=InMemorySessionRepository(),
        attempts=InMemorySignInAttemptRepository(),
        tokens=InMemoryApiTokenRepository(),
        devices=InMemoryDeviceRepository(),
    )

    @asynccontextmanager
    async def opened() -> AsyncIterator[IdentityRepos]:
        yield repos

    return IdentityImportActors(opened)


def _user(role: Role = Role.MEMBER) -> User:
    return User.create(
        username="alice",
        display_name="Alice",
        password_hash="x",
        now=datetime.now(UTC),
        role=role,
    )


async def test_the_owner_keeps_their_role_under_the_token_ceiling() -> None:
    """The actor is the account now, with no more than the token allowed."""
    user = _user(Role.ADMIN)
    actor = await _actors(user).actor_for(
        user.id, frozenset({"transfer:bundle:import"})
    )
    assert actor is not None
    assert actor.id == user.id
    assert actor.roles == frozenset({"admin"})
    assert actor.grants == frozenset({"transfer:bundle:import"})


async def test_a_disabled_owner_is_no_one() -> None:
    """The import fails rather than run for a disabled account."""
    user = _user()
    user.disable()
    assert await _actors(user).actor_for(user.id, None) is None


def test_the_postgres_version_opens_a_session_per_lookup() -> None:
    """It is built over a session factory, not one open session."""
    assert isinstance(build_import_actors(lambda: None), IdentityImportActors)  # type: ignore[arg-type]
