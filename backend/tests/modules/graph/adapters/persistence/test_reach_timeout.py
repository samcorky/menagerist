"""A multi-hop query that runs too long is cut off, not left to hold a worker."""

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import func, select, text

from app.modules.graph.adapters.persistence import reach_sql
from app.modules.graph.domain.reach import ReachTooLargeError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


async def test_a_slow_walk_is_cut_off(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Past the time limit the statement is cancelled and the caller is told."""
    monkeypatch.setattr(reach_sql, "WALK_TIMEOUT_MS", 50)

    with pytest.raises(ReachTooLargeError):
        await reach_sql.execute_walk(db_session, select(func.pg_sleep(2)))


async def test_the_limit_is_lifted_after_a_fast_walk(db_session: AsyncSession) -> None:
    """The limit covers the walk only, not what the request does next."""
    before = (await db_session.execute(text("SHOW statement_timeout"))).scalar_one()

    await reach_sql.execute_walk(db_session, select(func.pg_sleep(0)))

    after = (await db_session.execute(text("SHOW statement_timeout"))).scalar_one()
    assert after == before
