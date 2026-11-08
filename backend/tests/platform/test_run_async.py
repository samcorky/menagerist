"""`run_async` leaves no pooled connection behind for the next event loop."""

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
import sqlalchemy
from sqlalchemy.ext.asyncio import AsyncEngine

from app.platform.config import get_database_settings
from app.platform.database import get_engine, get_session_factory, run_async

if TYPE_CHECKING:
    from collections.abc import Iterator

_QUERY = sqlalchemy.text("SELECT 1")


@pytest.fixture
def cached_engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[AsyncMock]:
    """A cached engine that never connects, with `dispose` replaced by a spy."""
    monkeypatch.setenv(
        "MENAGERIST_DATABASE_URL", "postgresql+asyncpg://user:pw@localhost/none"
    )
    get_database_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    get_engine()
    dispose = AsyncMock()
    # `AsyncEngine` uses slots, so the spy goes on the class.
    monkeypatch.setattr(AsyncEngine, "dispose", dispose)
    yield dispose
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    get_database_settings.cache_clear()


async def _value() -> int:
    return 7


async def _fail() -> None:
    msg = "boom"
    raise RuntimeError(msg)


def test_returns_the_result(cached_engine: AsyncMock) -> None:
    """The coroutine's result comes back, and the engine is disposed."""
    assert run_async(_value()) == 7
    cached_engine.assert_awaited_once()


def test_disposes_the_engine_when_the_coroutine_raises(
    cached_engine: AsyncMock,
) -> None:
    """A failing command still releases its pooled connections."""
    with pytest.raises(RuntimeError, match="boom"):
        run_async(_fail())
    cached_engine.assert_awaited_once()


def test_does_not_build_an_engine_nobody_asked_for() -> None:
    """Commands that never touch the database do not need database settings."""
    get_engine.cache_clear()
    assert run_async(_value()) == 7
    assert get_engine.cache_info().currsize == 0


@pytest.mark.integration
def test_a_second_run_can_use_the_engine_the_first_one_pooled(
    postgres_url: str,
) -> None:
    """Without disposal the second loop is handed a connection from a closed loop."""
    del postgres_url

    async def query() -> None:
        async with get_engine().connect() as connection:
            await connection.execute(_QUERY)

    run_async(query())
    run_async(query())
