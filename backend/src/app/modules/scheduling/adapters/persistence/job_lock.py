"""Transaction-scoped coordination for a job's submissions and claims."""

from hashlib import sha256
from typing import TYPE_CHECKING

from sqlalchemy import func, select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _key(job_key: str) -> int:
    # Stable across processes; hash collisions only introduce extra contention.
    digest = sha256(f"menagerist:scheduling:{job_key}".encode()).digest()
    return int.from_bytes(digest[:8], signed=True)


async def lock_job(session: AsyncSession, job_key: str) -> None:
    """Hold the per-job lock until the caller commits or rolls back."""
    await session.execute(select(func.pg_advisory_xact_lock(_key(job_key))))


async def try_lock_job(session: AsyncSession, job_key: str) -> bool:
    """Skip a busy job without blocking claims for unrelated jobs."""
    return bool(
        await session.scalar(select(func.pg_try_advisory_xact_lock(_key(job_key))))
    )
