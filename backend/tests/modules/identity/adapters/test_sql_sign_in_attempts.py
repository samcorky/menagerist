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
from app.modules.identity.domain.throttle import (
    AttemptWindow,
    ThrottleKey,
    ThrottleKind,
)

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


async def _reserve_script(repo: SignInAttemptRepository) -> list[object]:
    """Count attempts, release some, and return what each step answered."""
    seen: list[object] = []
    for _ in range(3):
        seen.append(await repo.record_failure(KEY, limit=2, window=WINDOW, now=NOW))
    window_start = NOW
    seen.append(await repo.locked_keys([KEY], now=NOW))
    await repo.release_attempt(KEY, window_start=window_start, limit=2)
    seen.append(await repo.locked_keys([KEY], now=NOW))
    await repo.release_attempt(KEY, window_start=window_start, limit=2)
    seen.append(await repo.record_failure(KEY, limit=2, window=WINDOW, now=NOW))
    # A release for another window, or for no key, changes nothing.
    await repo.release_attempt(KEY, window_start=NOW - timedelta(minutes=1), limit=2)
    await repo.release_attempt(OTHER, window_start=NOW, limit=2)
    seen.append(await repo.record_failure(KEY, limit=2, window=WINDOW, now=NOW))
    return seen


async def test_sql_reserving_and_releasing_match_the_in_memory_twin(
    db_session: AsyncSession,
) -> None:
    """Counts, locks and releases agree between the two implementations."""
    memory = await _reserve_script(InMemorySignInAttemptRepository())
    sql = await _reserve_script(SqlAlchemySignInAttemptRepository(db_session))

    assert sql == memory
    assert memory[2] == AttemptWindow(
        count=3, window_start=NOW, locked_until=NOW + WINDOW
    )
    assert memory[5] == AttemptWindow(
        count=2, window_start=NOW, locked_until=NOW + WINDOW
    )
