import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import text

from app.modules.system.adapters.platform.checks._util import (
    failed_observation,
    observation,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.system.domain.readiness import CheckObservation


class DatabaseConnectivityCheck:
    """Verifies the database is reachable and reports response time + version.

    Both metrics share a single session/connection, so they are reported by one
    check rather than two.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def run(self) -> Mapping[str, CheckObservation]:
        """Query the database once and derive both observations from it."""
        now = datetime.now(UTC)
        # Broad Exception here: asyncpg pool-connect failures (e.g. connection
        # refused) propagate as raw OSError - SQLAlchemy only wraps errors at
        # statement-execution time, not pool-connect time. Catching only
        # SQLAlchemyError would let those surface as unhandled 500s instead of a
        # fail observation.
        try:
            async with self._session_factory() as session:
                t0 = time.perf_counter()
                await session.execute(text("SELECT 1"))
                elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

                row = await session.execute(text("SHOW server_version"))
                db_version: str = row.scalar_one()

            return {
                "database:responseTime": observation(elapsed_ms, "ms", now=now),
                "database:version": observation(db_version, "version", now=now),
            }
        except Exception as exc:
            return {
                "database:responseTime": failed_observation("ms", now=now, exc=exc),
                "database:version": failed_observation("version", now=now, exc=exc),
            }
