"""Advisory lock keys are stable and the session lock excludes other holders."""

import asyncio
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import create_async_engine

from app.platform.advisory_locks import AdvisoryLock, session_lock

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncEngine

PINNED_KEYS = {
    AdvisoryLock.SETUP: -2487852955842342286,
    AdvisoryLock.ADMIN: -3478567907107284073,
    AdvisoryLock.BACKUP_RESTORE: 3620452567116458444,
    AdvisoryLock.MIGRATION: 7494565131980497318,
}


def test_keys_are_pinned() -> None:
    """A rename or edit must not change a key without this test noticing."""
    assert {lock: lock.key for lock in AdvisoryLock} == PINNED_KEYS


def test_keys_are_unique_signed_64_bit() -> None:
    """Postgres takes a signed bigint, and two locks must never share a key."""
    keys = [lock.key for lock in AdvisoryLock]
    assert len(set(keys)) == len(keys)
    assert all(-(2**63) <= key < 2**63 for key in keys)


@pytest.fixture
async def engine(postgres_url: str) -> AsyncIterator[AsyncEngine]:
    """Give the lock holders a pool of their own."""
    engine = create_async_engine(postgres_url)
    try:
        yield engine
    finally:
        await engine.dispose()


async def _try_xact_lock(engine: AsyncEngine, lock: AdvisoryLock) -> bool:
    """Report whether a transaction-level lock on `lock` is free right now."""
    async with engine.begin() as connection:
        return bool(
            await connection.scalar(select(func.pg_try_advisory_xact_lock(lock.key)))
        )


@pytest.mark.integration
async def test_session_lock_excludes_transaction_locks_and_releases(
    engine: AsyncEngine,
) -> None:
    """A restore's transaction lock cannot overlap a held migration lock."""
    async with session_lock(engine, AdvisoryLock.MIGRATION):
        assert not await _try_xact_lock(engine, AdvisoryLock.MIGRATION)
        assert await _try_xact_lock(engine, AdvisoryLock.SETUP)
    assert await _try_xact_lock(engine, AdvisoryLock.MIGRATION)


@pytest.mark.integration
async def test_session_lock_releases_after_an_error(engine: AsyncEngine) -> None:
    """A failed migration must not leave the next instance waiting."""
    with pytest.raises(RuntimeError, match="boom"):
        async with session_lock(engine, AdvisoryLock.MIGRATION):
            raise RuntimeError("boom")
    assert await _try_xact_lock(engine, AdvisoryLock.MIGRATION)


@pytest.mark.integration
async def test_concurrent_holders_run_one_at_a_time(engine: AsyncEngine) -> None:
    """Instances starting together take turns, so a check-then-act runs once."""
    migrated = False
    migrations = 0
    inside = 0
    overlap = 0

    async def instance() -> None:
        nonlocal migrated, migrations, inside, overlap
        async with session_lock(engine, AdvisoryLock.MIGRATION):
            inside += 1
            overlap = max(overlap, inside)
            if not migrated:
                await asyncio.sleep(0.05)
                migrated = True
                migrations += 1
            inside -= 1

    await asyncio.gather(*(instance() for _ in range(6)))
    assert migrations == 1
    assert overlap == 1
