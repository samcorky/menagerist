"""Concurrent first-run setups and admin changes against real Postgres."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.entrypoints.api.shared.authorization import RoleAuthorizationAdapter
from app.modules.identity.adapters.persistence.models import SessionModel, UserModel
from app.modules.identity.adapters.persistence.session_repository import (
    SqlAlchemySessionRepository,
)
from app.modules.identity.adapters.persistence.sign_in_attempt_repository import (
    SqlAlchemySignInAttemptRepository,
)
from app.modules.identity.adapters.persistence.unit_of_work import create_identity_uow
from app.modules.identity.adapters.persistence.user_repository import (
    SqlAlchemyUserRepository,
)
from app.modules.identity.adapters.security.in_memory_password_hasher import (
    InMemoryPasswordHasher,
)
from app.modules.identity.adapters.security.session_token_generator import (
    SecretsSessionTokenGenerator,
)
from app.modules.identity.application.setup_first_admin import (
    SetupFirstAdmin,
    SetupFirstAdminCommand,
)
from app.modules.identity.application.update_user import UpdateUser, UpdateUserCommand
from app.modules.identity.application.user_listing import UserListing
from app.modules.identity.domain.errors import (
    LastAdministratorError,
    SetupAlreadyDoneError,
)
from app.modules.identity.domain.user import Role, User
from app.modules.identity.ports.existing_data_claim import ClaimReport
from app.modules.identity.ports.unit_of_work import IdentityRepos, IdentityUnitOfWork
from app.platform.unit_of_work import SqlAlchemySessionUnitOfWork
from app.shared_kernel.actor import ANONYMOUS_ACTOR, Actor

if TYPE_CHECKING:
    import uuid
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


class _SlowClaim:
    """Widens the window between the insert and the commit."""

    def __init__(self) -> None:
        self.calls = 0

    async def claim(self, owner_id: uuid.UUID) -> ClaimReport:
        """Pause, then report nothing."""
        self.calls += 1
        await asyncio.sleep(0.3)
        return ClaimReport()


@pytest_asyncio.fixture
async def factory(
    postgres_url: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """A session factory over committing connections; empties the tables after."""
    engine = create_async_engine(postgres_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield sessions
    finally:
        async with sessions.begin() as session:
            await session.execute(delete(SessionModel))
            await session.execute(delete(UserModel))
        await engine.dispose()


def _setup(
    sessions: async_sessionmaker[AsyncSession], claim: _SlowClaim
) -> SetupFirstAdmin:
    return SetupFirstAdmin(
        create_identity_uow(sessions),
        InMemoryPasswordHasher(),
        SecretsSessionTokenGenerator(),
        claim,
        session_ttl=timedelta(hours=1),
    )


def _command(username: str) -> SetupFirstAdminCommand:
    return SetupFirstAdminCommand(
        username=username, display_name="Admin", password="password-123"
    )


async def _user_count(sessions: async_sessionmaker[AsyncSession]) -> int:
    async with sessions() as session:
        return (
            await session.execute(select(func.count()).select_from(UserModel))
        ).scalar_one()


@pytest.mark.parametrize(
    ("second", "label"), [("other", "different"), ("first", "same")]
)
async def test_concurrent_setups_create_exactly_one_admin(
    factory: async_sessionmaker[AsyncSession], second: str, label: str
) -> None:
    """One setup wins; the other gets SetupAlreadyDoneError, never a 500."""
    claim = _SlowClaim()
    results = await asyncio.gather(
        _setup(factory, claim).handle(_command("first"), ANONYMOUS_ACTOR),
        _setup(factory, claim).handle(_command(second), ANONYMOUS_ACTOR),
        return_exceptions=True,
    )

    failures = [r for r in results if isinstance(r, BaseException)]
    assert len(failures) == 1, label
    assert isinstance(failures[0], SetupAlreadyDoneError)
    assert await _user_count(factory) == 1
    assert claim.calls == 1


class _SlowSessionRepository(SqlAlchemySessionRepository):
    """Pauses after the last-admin check so overlapping requests really overlap."""

    async def delete_for_user(self, user_id: uuid.UUID) -> int:
        await asyncio.sleep(0.3)
        return await super().delete_for_user(user_id)


def _slow_uow(factory: async_sessionmaker[AsyncSession]) -> IdentityUnitOfWork:
    def build(session: AsyncSession) -> IdentityRepos:
        return IdentityRepos(
            users=SqlAlchemyUserRepository(session),
            sessions=_SlowSessionRepository(session),
            attempts=SqlAlchemySignInAttemptRepository(session),
        )

    return SqlAlchemySessionUnitOfWork(factory, build)


async def _add_admins(factory: async_sessionmaker[AsyncSession]) -> list[User]:
    hasher = InMemoryPasswordHasher()
    admins = [
        User.create(
            username=name,
            display_name=name,
            password_hash=hasher.hash("password-123"),
            now=datetime.now(UTC),
            role=Role.ADMIN,
        )
        for name in ("alpha", "bravo")
    ]
    async with factory.begin() as session:
        repo = SqlAlchemyUserRepository(session)
        for admin in admins:
            await repo.add(admin)
    return admins


async def _disable(
    factory: async_sessionmaker[AsyncSession], target: User, by: User
) -> UserListing:
    return await UpdateUser(_slow_uow(factory), RoleAuthorizationAdapter()).handle(
        UpdateUserCommand(user_id=target.id, disabled=True),
        Actor(id=by.id, roles=frozenset({"admin"})),
    )


async def test_two_admins_cannot_disable_each_other_concurrently(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """Exactly one succeeds and one gets LastAdministratorError: no deadlock."""
    alpha, bravo = await _add_admins(factory)

    results = await asyncio.gather(
        _disable(factory, bravo, alpha),
        _disable(factory, alpha, bravo),
        return_exceptions=True,
    )

    assert sum(isinstance(r, UserListing) for r in results) == 1
    assert sum(isinstance(r, LastAdministratorError) for r in results) == 1
    async with factory() as session:
        active = (
            await session.execute(
                select(func.count())
                .select_from(UserModel)
                .where(UserModel.disabled.is_(False))
            )
        ).scalar_one()
    assert active == 1


async def test_admin_changes_wait_for_the_admin_lock(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """An update blocks while another transaction holds the lock, then proceeds."""
    alpha, bravo = await _add_admins(factory)
    holder = factory()
    await SqlAlchemyUserRepository(holder).lock_admin_changes()

    task = asyncio.create_task(_disable(factory, bravo, alpha))
    done, _ = await asyncio.wait({task}, timeout=0.5)
    assert not done

    await holder.rollback()
    await holder.close()
    updated = await asyncio.wait_for(task, timeout=5)
    assert updated.user.disabled
