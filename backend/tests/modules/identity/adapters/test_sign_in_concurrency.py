import asyncio
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.identity.adapters.persistence.models import UserModel
from app.modules.identity.adapters.persistence.unit_of_work import create_identity_uow
from app.modules.identity.adapters.persistence.user_repository import (
    SqlAlchemyUserRepository,
)
from app.modules.identity.adapters.security.in_memory_password_hasher import (
    InMemoryPasswordHasher,
)
from app.modules.identity.adapters.security.password_authenticator import (
    PasswordAuthenticator,
)
from app.modules.identity.domain.errors import SignInThrottledError
from app.modules.identity.domain.user import User
from app.modules.identity.ports.authenticator import PasswordCredentials

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def factory(
    postgres_url: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """A session factory over real, committing connections; removes its users."""
    engine = create_async_engine(postgres_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield sessions
    finally:
        async with sessions.begin() as session:
            await session.execute(delete(UserModel))
        await engine.dispose()


async def _add_user(sessions: async_sessionmaker[AsyncSession]) -> User:
    user = User.create(
        username="racer",
        display_name="Racer",
        password_hash=InMemoryPasswordHasher().hash("password-123"),
        now=datetime.now(UTC),
    )
    async with sessions.begin() as session:
        await SqlAlchemyUserRepository(session).add(user)
    return user


async def test_parallel_wrong_guesses_cannot_bypass_the_throttle(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """Eight parallel wrong guesses: exactly five count, the rest are throttled."""
    await _add_user(factory)
    hasher = InMemoryPasswordHasher()

    async def attempt() -> object:
        auth = PasswordAuthenticator(
            create_identity_uow(factory), hasher, decoy_hash="fake$decoy"
        )
        try:
            return await auth.authenticate(
                PasswordCredentials(username="racer", password="wrong-password")
            )
        except SignInThrottledError as exc:
            return exc

    results = await asyncio.gather(*(attempt() for _ in range(8)))

    assert sum(r is None for r in results) == 5
    assert sum(isinstance(r, SignInThrottledError) for r in results) == 3
    async with factory() as session:
        stored = await SqlAlchemyUserRepository(session).get_by_username("racer")
    assert stored is not None
    assert stored.failed_attempts == 5


async def test_locked_row_blocks_a_concurrent_locking_read_until_commit(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """While a sign-in holds the row, another locking read waits for the commit."""
    user = await _add_user(factory)
    async with factory() as holder, factory() as other:
        await SqlAlchemyUserRepository(holder).get_by_username_for_update("racer")
        waiting = asyncio.create_task(
            SqlAlchemyUserRepository(other).get_by_username_for_update("racer")
        )
        done, _ = await asyncio.wait({waiting}, timeout=0.5)
        assert not done
        await holder.commit()
        found = await asyncio.wait_for(waiting, timeout=5)
        assert found is not None
        assert found.id == user.id


class _SlowHasher(InMemoryPasswordHasher):
    def verify(self, password: str, hashed: str) -> bool:
        time.sleep(0.5)
        return super().verify(password, hashed)


async def test_slow_verify_does_not_hold_a_connection(postgres_url: str) -> None:
    """Six slow logins on a pool of two finish promptly and leave room for others."""
    engine = create_async_engine(
        postgres_url, pool_size=1, max_overflow=1, pool_timeout=3
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    hasher = _SlowHasher()

    async def attempt(name: str) -> object:
        auth = PasswordAuthenticator(
            create_identity_uow(sessions), hasher, decoy_hash="fake$decoy"
        )
        return await auth.authenticate(
            PasswordCredentials(username=name, password="wrong-password")
        )

    async def unrelated_query() -> int:
        await asyncio.sleep(0.2)
        started = time.monotonic()
        async with sessions() as session:
            await session.execute(select(1))
        return int((time.monotonic() - started) * 1000)

    try:
        started = time.monotonic()
        query_task = asyncio.create_task(unrelated_query())
        results = await asyncio.gather(*(attempt(f"nobody{i}") for i in range(6)))
        query_ms = await query_task
        elapsed = time.monotonic() - started
    finally:
        await engine.dispose()

    assert results == [None] * 6
    assert query_ms < 400
    assert elapsed < 3
