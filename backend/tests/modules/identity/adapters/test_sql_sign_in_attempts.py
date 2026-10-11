"""The Postgres failure counters behave like the in-memory twin."""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from app.modules.identity.adapters.persistence.in_memory_sign_in_attempt_repository import (  # noqa: E501
    InMemorySignInAttemptRepository,
)
from app.modules.identity.adapters.persistence.sign_in_attempt_repository import (
    SqlAlchemySignInAttemptRepository,
)
from app.modules.identity.domain.throttle import ThrottleKey, ThrottleKind

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.identity.ports.sign_in_attempt_repository import (
        SignInAttemptRepository,
    )

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
WINDOW = timedelta(minutes=15)
KEY = ThrottleKey(kind=ThrottleKind.USERNAME, digest="a" * 64)
OTHER = ThrottleKey(kind=ThrottleKind.IP, digest="b" * 64)


async def _script(repo: SignInAttemptRepository) -> list[dict[ThrottleKey, datetime]]:
    """Run a fixed sequence of failures and lock checks; return what was seen."""
    seen = []
    for minute in (0, 1, 2, 3):
        await repo.record_failure(
            KEY, limit=5, window=WINDOW, now=NOW + timedelta(minutes=minute)
        )
        seen.append(await repo.locked_keys([KEY, OTHER], now=NOW))
    await repo.record_failure(OTHER, limit=1, window=WINDOW, now=NOW)
    seen.append(await repo.locked_keys([KEY, OTHER], now=NOW))
    await repo.record_failure(
        KEY, limit=5, window=WINDOW, now=NOW + timedelta(minutes=4)
    )
    seen.append(await repo.locked_keys([KEY, OTHER], now=NOW + timedelta(minutes=5)))
    # Still locked until the window (started at NOW) ends; free just after.
    seen.append(await repo.locked_keys([KEY], now=NOW + WINDOW - timedelta(seconds=1)))
    seen.append(await repo.locked_keys([KEY], now=NOW + WINDOW))
    # A failure after the window starts a fresh count.
    await repo.record_failure(KEY, limit=5, window=WINDOW, now=NOW + WINDOW)
    seen.append(await repo.locked_keys([KEY], now=NOW + WINDOW))
    await repo.clear(KEY)
    await repo.clear(KEY)
    seen.append(await repo.locked_keys([KEY, OTHER], now=NOW))
    return seen


async def test_sql_counters_match_the_in_memory_twin(db_session: AsyncSession) -> None:
    """The same script gives the same lock answers in both implementations."""
    memory = await _script(InMemorySignInAttemptRepository())
    sql = await _script(SqlAlchemySignInAttemptRepository(db_session))

    assert sql == memory
    assert memory[3] == {}
    assert memory[5] == {KEY: NOW + WINDOW, OTHER: NOW + WINDOW}


async def test_sql_delete_stale_removes_only_finished_windows(
    db_session: AsyncSession,
) -> None:
    """Counters whose window ended are swept; live ones stay."""
    repo = SqlAlchemySignInAttemptRepository(db_session)
    await repo.record_failure(KEY, limit=1, window=WINDOW, now=NOW)
    await repo.record_failure(OTHER, limit=1, window=WINDOW, now=NOW + WINDOW)

    removed = await repo.delete_stale(window=WINDOW, now=NOW + WINDOW)

    assert removed == 1
    assert await repo.locked_keys([KEY], now=NOW) == {}
    assert OTHER in await repo.locked_keys([OTHER], now=NOW + WINDOW)


async def test_sql_locked_keys_with_no_keys_is_empty(db_session: AsyncSession) -> None:
    """No keys means no query and no locks."""
    assert (
        await SqlAlchemySignInAttemptRepository(db_session).locked_keys([], now=NOW)
        == {}
    )
