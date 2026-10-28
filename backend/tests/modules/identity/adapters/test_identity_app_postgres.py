"""The `identity` CLI on real Postgres, including the existing-data claim."""

import asyncio
import uuid
from typing import TYPE_CHECKING

import pytest
import sqlalchemy
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.entrypoints.cli  # noqa: F401  (wires the real claim into the CLI)
from app.modules.graph.adapters.persistence.unit_of_work import build_graph_repos
from app.modules.graph.domain.node import Node
from app.modules.identity.adapters.cli.identity_app import (
    create_admin,
    list_accounts,
    reset_password,
)
from app.platform.database import get_engine, get_session_factory

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = pytest.mark.integration

PASSWORD_ENV_VAR = "MENAGERIST_IDENTITY_INITIAL_PASSWORD"

PASSWORD = "a very secret passphrase"


@pytest.fixture
def database(
    postgres_url: str, postgres_sync_url: str, monkeypatch: pytest.MonkeyPatch
) -> Iterator[str]:
    """An empty users table and one ownerless item; cleaned afterwards."""

    def wipe() -> None:
        engine = sqlalchemy.create_engine(postgres_sync_url)
        with engine.begin() as connection:
            for table in ("sessions", "users", "edges", "nodes"):
                connection.execute(sqlalchemy.text(f"DELETE FROM {table}"))
        engine.dispose()

    async def seed() -> None:
        engine = create_async_engine(postgres_url)
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            node = Node.create(owner_id=uuid.UUID(int=0), name="legacy")
            node.owner_id = None
            await build_graph_repos(session).nodes.add(node)
            await session.commit()
        await engine.dispose()

    wipe()
    asyncio.run(seed())
    monkeypatch.setenv(PASSWORD_ENV_VAR, PASSWORD)
    try:
        yield postgres_sync_url
    finally:
        get_session_factory.cache_clear()
        get_engine.cache_clear()
        wipe()


def _fresh_engine() -> None:
    """Each command runs its own event loop, so drop the pooled connections."""
    get_session_factory.cache_clear()
    get_engine.cache_clear()


def _rows(sync_url: str, sql: str) -> list[tuple[object, ...]]:
    engine = sqlalchemy.create_engine(sync_url)
    with engine.connect() as connection:
        rows = [tuple(row) for row in connection.execute(sqlalchemy.text(sql))]
    engine.dispose()
    return rows


def test_create_admin_reset_password_and_list(
    database: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """First admin claims existing data; a second does not; reset forces a change."""
    create_admin(username="sam")
    first = _rows(database, "SELECT id, role, password_expired FROM users")
    assert [(row[1], row[2]) for row in first] == [("admin", False)]
    assert _rows(database, "SELECT owner_id FROM nodes") == [(first[0][0],)]
    assert "1 items" in capsys.readouterr().out

    _fresh_engine()
    create_admin(username="bob")
    _fresh_engine()
    reset_password(username="bob", from_settings=True)
    _fresh_engine()
    list_accounts()

    bob = _rows(
        database,
        "SELECT role, password_expired FROM users WHERE username = 'bob'",
    )
    assert bob == [("admin", True)]
    assert _rows(database, "SELECT owner_id FROM nodes") == [(first[0][0],)]
    out = capsys.readouterr().out
    rows = out.splitlines()
    assert any("sam" in r and "admin" in r and "active" in r for r in rows)
    assert any("bob" in r and "admin" in r and "active" in r for r in rows)
    assert "scrypt$" not in out
