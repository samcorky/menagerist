"""Shared execution reservations must conflict with every exclusive restore."""

import asyncio
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.scheduling.adapters.platform.restore_guard import (
    SqlAlchemyRestoreGuard,
)
from app.platform.advisory_locks import BACKUP_RESTORE_LOCK_KEY

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


@pytest.fixture
async def factory(postgres_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Give each lock holder its own connection and transaction."""
    engine = create_async_engine(postgres_url)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def test_shared_executions_coexist_and_exclude_restore(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """Two executing jobs may hold the guard, but an exclusive restore cannot."""
    guard = SqlAlchemyRestoreGuard(factory)
    async with guard.try_hold() as first, guard.try_hold() as second:
        assert first
        assert second
        async with factory.begin() as session:
            assert not await session.scalar(
                select(func.pg_try_advisory_xact_lock(BACKUP_RESTORE_LOCK_KEY))
            )
    async with factory.begin() as session:
        assert await session.scalar(
            select(func.pg_try_advisory_xact_lock(BACKUP_RESTORE_LOCK_KEY))
        )


async def test_exclusive_restore_refuses_execution_without_waiting(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """An API-style exclusive restore makes the shared try-lock return false."""
    async with factory.begin() as session:
        await session.execute(
            select(func.pg_advisory_xact_lock(BACKUP_RESTORE_LOCK_KEY))
        )
        async with (
            asyncio.timeout(2),
            SqlAlchemyRestoreGuard(factory).try_hold() as held,
        ):
            assert not held


async def test_cancelled_execution_releases_shared_lock(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """Cancelling the guard owner rolls back its lock-holding transaction."""
    entered = asyncio.Event()

    async def execution() -> None:
        async with SqlAlchemyRestoreGuard(factory).try_hold() as held:
            assert held
            entered.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(execution())
    await asyncio.wait_for(entered.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with factory.begin() as session:
        assert await session.scalar(
            select(func.pg_try_advisory_xact_lock(BACKUP_RESTORE_LOCK_KEY))
        )
