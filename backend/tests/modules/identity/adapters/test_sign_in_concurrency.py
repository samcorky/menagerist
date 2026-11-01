import asyncio
import time
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.identity.adapters.persistence.models import (
    SessionModel,
    SignInAttemptModel,
    UserModel,
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
from app.modules.identity.adapters.security.password_authenticator import (
    PasswordAuthenticator,
)
from app.modules.identity.adapters.security.session_token_generator import (
    SecretsSessionTokenGenerator,
)
from app.modules.identity.application.change_password import (
    ChangePassword,
    ChangePasswordCommand,
)
from app.modules.identity.application.sign_in import SignIn, SignInCommand
from app.modules.identity.application.sign_in_throttle import SignInThrottle
from app.modules.identity.domain.errors import (
    InvalidCredentialsError,
    SignInThrottledError,
)
from app.modules.identity.domain.throttle import ThrottleKey, ThrottleKind
from app.modules.identity.domain.user import User
from app.modules.identity.ports.authenticator import PasswordCredentials
from app.shared_kernel.actor import ANONYMOUS_ACTOR, Actor

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.identity.ports.authenticator import VerifiedIdentity

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
            await session.execute(delete(SessionModel))
            await session.execute(delete(UserModel))
            await session.execute(delete(SignInAttemptModel))
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


async def test_parallel_failures_are_all_counted_and_lock_once(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """Eight parallel failures on one key: none is lost, and the key is locked."""
    key = ThrottleKey(kind=ThrottleKind.USERNAME, digest="racer-digest")
    now = datetime.now(UTC)

    async def fail() -> None:
        async with factory.begin() as session:
            await SqlAlchemySignInAttemptRepository(session).record_failure(
                key, limit=5, window=timedelta(minutes=15), now=now
            )

    await asyncio.gather(*(fail() for _ in range(8)))

    async with factory() as session:
        row = (
            await session.execute(
                select(SignInAttemptModel).where(
                    SignInAttemptModel.key_hash == key.digest
                )
            )
        ).scalar_one()
        locked = await SqlAlchemySignInAttemptRepository(session).locked_keys(
            [key], now=now
        )
    assert row.failure_count == 8
    assert locked == {key: now + timedelta(minutes=15)}


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


class _CountingHasher(InMemoryPasswordHasher):
    def __init__(self) -> None:
        self.guesses = 0

    def verify(self, password: str, hashed: str) -> bool:
        if password != "decoy":
            self.guesses += 1
        return super().verify(password, hashed)


async def test_parallel_guesses_never_verify_more_than_the_limit(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """Thirty parallel wrong guesses from distinct addresses: five are checked."""
    await _add_user(factory)
    hasher = _CountingHasher()

    def new_sign_in() -> SignIn:
        # One unit of work per request, as in the app.
        return SignIn(
            create_identity_uow(factory),
            get_access_guard(),
            PasswordAuthenticator(
                create_identity_uow(factory), hasher, decoy_hash="fake$decoy"
            ),
            SecretsSessionTokenGenerator(),
            hasher,
            SignInThrottle(),
            decoy_hash=hasher.hash("decoy"),
            session_ttl=timedelta(hours=1),
        )

    async def guess(i: int) -> str:
        try:
            await new_sign_in().handle(
                SignInCommand(
                    username="racer", password=f"wrong-{i}", client_ip=f"10.0.0.{i}"
                ),
                ANONYMOUS_ACTOR,
            )
        except (InvalidCredentialsError, SignInThrottledError) as error:
            return type(error).__name__
        raise AssertionError("a wrong password signed in")

    outcomes = await asyncio.gather(*(guess(i) for i in range(30)))

    assert hasher.guesses == 5
    assert outcomes.count("InvalidCredentialsError") == 5
    assert outcomes.count("SignInThrottledError") == 25


async def test_a_password_change_between_check_and_session_voids_the_sign_in(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """On Postgres the old password cannot mint a session after a change."""
    user = await _add_user(factory)
    hasher = InMemoryPasswordHasher()
    tokens = SecretsSessionTokenGenerator()
    throttle = SignInThrottle()
    change = ChangePassword(
        create_identity_uow(factory),
        get_access_guard(),
        hasher,
        tokens,
        throttle,
        session_ttl=timedelta(hours=1),
    )

    class _Racing:
        def __init__(self) -> None:
            self.inner = PasswordAuthenticator(
                create_identity_uow(factory), hasher, decoy_hash="fake$decoy"
            )

        async def authenticate(self, credentials: object) -> VerifiedIdentity | None:
            identity = await self.inner.authenticate(credentials)  # type: ignore[arg-type]
            await change.handle(
                ChangePasswordCommand(
                    current_password="password-123",
                    new_password="a-much-better-one",
                ),
                Actor(id=user.id, roles=frozenset({"member"})),
            )
            return identity

    sign_in = SignIn(
        create_identity_uow(factory),
        get_access_guard(),
        _Racing(),
        tokens,
        hasher,
        throttle,
        decoy_hash="fake$decoy",
        session_ttl=timedelta(hours=1),
    )

    with pytest.raises(InvalidCredentialsError):
        await sign_in.handle(
            SignInCommand(username="racer", password="password-123"), ANONYMOUS_ACTOR
        )

    async with factory() as session:
        count = len((await session.execute(select(SessionModel.id))).scalars().all())
    assert count == 1  # only the one ChangePassword started
