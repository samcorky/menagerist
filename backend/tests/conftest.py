import uuid
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.testclient import TestClient
from testcontainers.community.postgres import PostgresContainer

from app.entrypoints.api.shared.dependencies import get_current_actor
from app.platform import alembic_runner
from app.platform.config import get_database_settings, get_identity_settings
from app.shared_kernel.actor import Actor

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Iterator

    from fastapi import FastAPI


@pytest.fixture(scope="session")
def monkeypatch_session() -> Iterator[pytest.MonkeyPatch]:
    """Session-scoped equivalent of the built-in function-scoped `monkeypatch`."""
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    """Start a single Postgres container for the whole test session."""
    with PostgresContainer("postgres:18-alpine") as postgres:
        yield postgres


@pytest.fixture(scope="session")
def postgres_url(
    postgres_container: PostgresContainer, monkeypatch_session: pytest.MonkeyPatch
) -> str:
    """The async (asyncpg) connection url, migrated to head once per session."""
    url = postgres_container.get_connection_url(driver="asyncpg")
    monkeypatch_session.setenv("MENAGERIST_DATABASE_URL", url)
    get_database_settings.cache_clear()
    alembic_runner.upgrade()
    return url


@pytest.fixture(scope="session")
def postgres_sync_url(postgres_container: PostgresContainer) -> str:
    """A sync (psycopg) connection url to the same database.

    For tooling that doesn't support async engines - e.g. pytest-alembic's
    `alembic_engine`, which reflects the schema directly rather than through
    our async `env.py`.
    """
    return postgres_container.get_connection_url(driver="psycopg")


@pytest_asyncio.fixture
async def db_session(postgres_url: str) -> AsyncIterator[AsyncSession]:
    """A session scoped to one transaction, rolled back after the test.

    Repository code under test calls `session.commit()` itself (via the real
    unit of work) - `join_transaction_mode="create_savepoint"` lets those
    commits release a savepoint instead of the outer transaction, so the
    rollback below still discards everything the test wrote.
    """
    engine = create_async_engine(postgres_url)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session_factory = async_sessionmaker(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        session = session_factory()
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()
    await engine.dispose()


TEST_CSRF_TOKEN = "test-csrf-token"
DEFAULT_MEMBER_ID = uuid.UUID(int=1)


def actor_for(user_id: uuid.UUID, role: str = "member") -> Actor:
    """Build the actor a signed-in user with `role` would produce."""
    return Actor(id=user_id, roles=frozenset({role}))


def as_user(app: FastAPI, user_id: uuid.UUID, role: str = "member") -> None:
    """Make every request to `app` run as the given user."""
    actor = actor_for(user_id, role)
    app.dependency_overrides[get_current_actor] = lambda: actor


@pytest.fixture(autouse=True)
def _csrf_for_test_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give every TestClient a matching CSRF cookie and header.

    The production rule is unchanged: the CSRF tests remove both to prove it.
    """
    original_init = TestClient.__init__
    settings = get_identity_settings()

    def init(self: TestClient, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        original_init(self, *args, **kwargs)
        host = self.base_url.host
        self.cookies.set(
            settings.csrf_cookie_name,
            TEST_CSRF_TOKEN,
            # The cookie jar files dotless hosts under "<host>.local".
            domain=host if "." in host else f"{host}.local",
            path="/",
        )
        self.headers["X-CSRF-Token"] = TEST_CSRF_TOKEN

    monkeypatch.setattr(TestClient, "__init__", init)


@pytest.fixture(autouse=True)
def _default_actor_for_test_clients(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run every TestClient's app as a member, unless a test overrides it.

    Tests that exercise the real session lookup are marked `real_actor`; tests
    needing other people use `as_user`.
    """
    if request.node.get_closest_marker("real_actor"):
        return
    original_init = TestClient.__init__
    actor = actor_for(DEFAULT_MEMBER_ID)

    def init(self: TestClient, app: Any, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        original_init(self, app, *args, **kwargs)
        if hasattr(app, "dependency_overrides"):
            app.dependency_overrides.setdefault(get_current_actor, lambda: actor)

    monkeypatch.setattr(TestClient, "__init__", init)


@pytest.fixture(name="as_user")
def _as_user_fixture() -> Callable[..., None]:
    """Return `as_user(app, user_id, role="member")` for multi-user router tests."""
    return as_user
