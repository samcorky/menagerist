"""Postgres shared execution reservations against the existing restore lock."""

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from app.platform.advisory_locks import BACKUP_RESTORE_LOCK_KEY

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class SqlAlchemyRestoreGuard:
    """Keep a shared transaction lock for the whole execution and its cleanup."""

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    @asynccontextmanager
    async def try_hold(self) -> AsyncIterator[bool]:
        """Skip an exclusive restore while allowing unrelated jobs to coexist."""
        async with self._factory() as session, session.begin():
            acquired = await session.scalar(
                select(func.pg_try_advisory_xact_lock_shared(BACKUP_RESTORE_LOCK_KEY))
            )
            yield bool(acquired)
