import uuid
from contextlib import ExitStack, contextmanager
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.testclient import TestClient
from testcontainers.community.postgres import PostgresContainer

from app.entrypoints.api.shared import settings_reader
from app.entrypoints.api.shared.dependencies import get_current_actor
from app.modules.settings.adapters.persistence.in_memory_setting_value_repository import (  # noqa: E501
    InMemorySettingValueRepository,
)
from app.modules.settings.adapters.persistence.unit_of_work import (
    create_in_memory_settings_uow,
)
from app.platform import alembic_runner
from app.platform.config import get_database_settings
from app.shared_kernel.actor import Actor

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Iterator

    from anyio.from_thread import BlockingPortal
    from fastapi import FastAPI

# Areas whose tests are all in-memory and quick (about 20 seconds in total), so a
# pre-commit hook can run them: `pytest -m fast`. Marked by location, so a new test in
# one of these folders is included without remembering a decorator.
_FAST_LAYERS = frozenset({"domain", "application"})
_FAST_TOP_LEVEL = frozenset({"shared_kernel", "architecture", "platform"})


def _is_fast(parts: tuple[str, ...], *, integration: bool) -> bool:
    if integration or "tests" not in parts:
        return False
    below = parts[parts.index("tests") + 1 :]
    if below[0] in _FAST_TOP_LEVEL:
        return True
    return below[0] == "modules" and len(below) > 3 and below[2] in _FAST_LAYERS


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark quick in-memory areas `fast`, and tests that start a container `docker`.

    A test needs Docker when it uses the `postgres_container` fixture (directly or
    through `db_session`) or is `integration`: those fetch `db_session` at run time
    with `request.getfixturevalue`, which fixture inspection cannot see.
    """
    for item in items:
        uses_container = "postgres_container" in getattr(item, "fixturenames", ())
        if uses_container or item.get_closest_marker("integration") is not None:
            item.add_marker(pytest.mark.docker)
        integration = item.get_closest_marker("integration") is not None
        if _is_fast(item.path.parts, integration=integration):
            item.add_marker(pytest.mark.fast)


@pytest.fixture(autouse=True)
def _no_colour(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep structlog off colorama.

    On Windows colorama swaps `sys.stdout` for the real stream the first time logging
    is configured, which defeats `capsys` for a test run on its own.
    """
    monkeypatch.setenv("NO_COLOR", "1")


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


DEFAULT_MEMBER_ID = uuid.UUID(int=1)


def actor_for(user_id: uuid.UUID, role: str = "member") -> Actor:
    """Build the actor a signed-in user with `role` would produce."""
    return Actor(id=user_id, roles=frozenset({role}))


def as_user(app: FastAPI, user_id: uuid.UUID, role: str = "member") -> None:
    """Make every request to `app` run as the given user."""
    actor = actor_for(user_id, role)
    app.dependency_overrides[get_current_actor] = lambda: actor


@pytest.fixture(autouse=True)
def _reuse_test_client_portals(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Share one portal per test for unmanaged clients and close every client.

    Explicit client contexts keep their own lifespan and portal.
    """
    original_init = TestClient.__init__
    original_factory = TestClient._portal_factory
    portal: BlockingPortal | None = None
    with ExitStack() as stack:

        def init(client: TestClient, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
            original_init(client, *args, **kwargs)
            stack.callback(client.close)

        @contextmanager
        def portal_factory(client: TestClient) -> Iterator[BlockingPortal]:
            nonlocal portal
            if client.portal is not None:
                yield client.portal
            else:
                if portal is None:
                    portal = stack.enter_context(original_factory(client))
                yield portal

        monkeypatch.setattr(TestClient, "__init__", init)
        monkeypatch.setattr(TestClient, "_portal_factory", portal_factory)
        yield


@pytest.fixture(autouse=True)
def _origin_for_test_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give every TestClient the app's own `Origin`, as a browser would.

    The same-origin rule is unchanged: the CSRF tests remove or change it.
    """
    original_init = TestClient.__init__

    def init(self: TestClient, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        original_init(self, *args, **kwargs)
        self.headers["Origin"] = str(self.base_url).rstrip("/")

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


@pytest.fixture
def settings_store() -> InMemorySettingValueRepository:
    """The saved settings values of this test; the reader and the API see the same."""
    return InMemorySettingValueRepository()


@pytest.fixture(autouse=True)
def _in_memory_settings(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    settings_store: InMemorySettingValueRepository,
) -> Iterator[None]:
    """Give each test its own empty settings store, so none reaches for Postgres.

    Integration tests keep the real database. The catalogue is rebuilt per test
    because it reads the deployment's environment, which tests change.
    """
    if request.node.get_closest_marker("integration") is not None:
        yield
        return
    monkeypatch.setattr(
        settings_reader,
        "settings_uow",
        lambda: create_in_memory_settings_uow(settings_store),
    )
    settings_reader.get_settings_catalogue.cache_clear()
    settings_reader.get_settings_reader.cache_clear()
    yield
    settings_reader.get_settings_catalogue.cache_clear()
    settings_reader.get_settings_reader.cache_clear()
