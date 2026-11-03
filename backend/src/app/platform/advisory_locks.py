"""Postgres advisory lock keys shared across instance operations.

Every lock lives in `AdvisoryLock`, so a key can never be reused by accident.
"""

import hashlib
from contextlib import asynccontextmanager
from enum import Enum
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import func, select

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncEngine

logger = structlog.get_logger()


def _derive_key(name: str) -> int:
    """Hash a lock name to a signed 64-bit key, the width Postgres takes."""
    digest = hashlib.blake2b(f"menagerist:{name}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)


class AdvisoryLock(Enum):
    """Named locks. The key comes from the name, so renaming one changes its key."""

    SETUP = "setup"
    ADMIN = "admin"
    BACKUP_RESTORE = "backup_restore"
    MIGRATION = "migration"

    @property
    def key(self) -> int:
        """Return the `bigint` key passed to the `pg_advisory_*` functions."""
        return _derive_key(self.value)


@asynccontextmanager
async def session_lock(engine: AsyncEngine, lock: AdvisoryLock) -> AsyncIterator[None]:
    """Hold a session-level lock on its own connection for the whole block.

    Unlike a transaction lock this outlives the transactions of whatever runs
    inside, and Postgres drops it if the process dies. Waits as long as needed.
    """
    async with engine.connect() as connection:
        connection = await connection.execution_options(isolation_level="AUTOCOMMIT")
        acquired = await connection.scalar(select(func.pg_try_advisory_lock(lock.key)))
        if not acquired:
            logger.info("waiting for advisory lock", lock=lock.value)
            await connection.execute(select(func.pg_advisory_lock(lock.key)))
        try:
            yield
        finally:
            try:
                await connection.execute(select(func.pg_advisory_unlock(lock.key)))
            except Exception:
                # Never hand a connection that may still hold the lock to the pool.
                await connection.invalidate()
                raise
