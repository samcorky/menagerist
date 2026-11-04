"""Each database test gets its own process-wide engine, so loops never cross."""

import pytest
import sqlalchemy

from app.platform.database import get_engine

pytestmark = pytest.mark.integration

_QUERY = sqlalchemy.text("SELECT 1")


async def test_first_test_leaves_a_pooled_connection(postgres_url: str) -> None:
    """Use the cached engine and leave its connection pooled, in this test's loop."""
    del postgres_url
    async with get_engine().connect() as connection:
        await connection.execute(_QUERY)


async def test_next_test_can_use_the_cached_engine(postgres_url: str) -> None:
    """A later test, in a new loop, must not be handed the earlier loop's connection.

    Run in order (as in one worker) this fails with "attached to a different loop"
    if the engine is shared between tests.
    """
    del postgres_url
    async with get_engine().connect() as connection:
        await connection.execute(_QUERY)
