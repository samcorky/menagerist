"""Shared fixtures: an all-in-memory identity world."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

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

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


@dataclass(kw_only=True)
class World:
    """Everything an identity test needs, all in memory."""

    users: InMemoryUserRepository
    sessions: InMemorySessionRepository
    attempts: InMemorySignInAttemptRepository
    uow: InMemoryUnitOfWork[IdentityRepos]


MakeUser = Callable[..., User]


@pytest.fixture
def world() -> World:
    """Return a fresh in-memory world."""
    users = InMemoryUserRepository()
    sessions = InMemorySessionRepository()
    attempts = InMemorySignInAttemptRepository()
    return World(
        users=users,
        sessions=sessions,
        attempts=attempts,
        uow=InMemoryUnitOfWork(
            IdentityRepos(users=users, sessions=sessions, attempts=attempts)
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
