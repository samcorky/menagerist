from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from app.platform import alembic_runner
from app.platform.database import load_database_settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator


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
    monkeypatch_session.setenv("DATABASE_URL", url)
    load_database_settings.cache_clear()
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
