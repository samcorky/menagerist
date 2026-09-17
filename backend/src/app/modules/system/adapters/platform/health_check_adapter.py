import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from sqlalchemy import text
from sqlalchemy.pool import QueuePool

from app.modules.system.domain.readiness import (
    CheckObservation,
    CheckStatus,
    ReadinessReport,
)
from app.platform.alembic_runner import code_head_revisions, db_current_revisions
from app.platform.database import get_engine

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def _observation(
    observed_value: float | str,
    observed_unit: str,
    *,
    now: datetime,
    status: CheckStatus = CheckStatus.PASS,
    output: str | None = None,
) -> CheckObservation:
    return CheckObservation(
        component_type="datastore",
        observed_value=observed_value,
        observed_unit=observed_unit,
        status=status,
        time=now,
        output=output,
    )


def _failed(unit: str, *, now: datetime, exc: Exception) -> CheckObservation:
    return _observation(
        "unknown", unit, now=now, status=CheckStatus.FAIL, output=str(exc)
    )


class DatabaseHealthCheckAdapter:
    """Verifies database connectivity, migration state, and pool utilisation."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def check(self) -> ReadinessReport:
        """Run all readiness checks and return their aggregate result."""
        now = datetime.now(UTC)
        checks: dict[str, CheckObservation] = {}

        # database:responseTime + database:version share a single session/connection.
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

            checks["database:responseTime"] = _observation(elapsed_ms, "ms", now=now)
            checks["database:version"] = _observation(db_version, "version", now=now)
        except Exception as exc:
            checks["database:responseTime"] = _failed("ms", now=now, exc=exc)
            checks["database:version"] = _failed("version", now=now, exc=exc)

        # database:migrationRevision - isolated try/except, same broad-catch rationale.
        code_revisions = code_head_revisions()
        code_rev_str = ", ".join(sorted(code_revisions)) if code_revisions else "none"
        try:
            db_revisions = await db_current_revisions(self._session_factory)
            db_rev_str = ", ".join(sorted(db_revisions)) if db_revisions else "none"
            migration_ok = set(db_revisions) == set(code_revisions)
            mismatch = f"database at {db_rev_str}, code expects {code_rev_str}"
            checks["database:migrationRevision"] = _observation(
                db_rev_str,
                "revision",
                now=now,
                status=CheckStatus.PASS if migration_ok else CheckStatus.FAIL,
                output=None if migration_ok else mismatch,
            )
        except Exception as exc:
            checks["database:migrationRevision"] = _failed("revision", now=now, exc=exc)

        # database:poolUtilization - pure in-process introspection, no I/O.
        # Checked after the above sessions close so checkedout() reflects idle state.
        pool_obj = cast(QueuePool, get_engine().pool)
        checkedout = pool_obj.checkedout()
        pool_size = pool_obj.size()
        pool_saturated = 0 < pool_size <= checkedout
        utilization = round(checkedout / pool_size * 100, 2) if pool_size > 0 else 0.0
        pool_output: str | None = (
            f"{checkedout}/{pool_size} connections checked out, 0 available"
            if pool_saturated
            else None
        )
        checks["database:poolUtilization"] = _observation(
            utilization,
            "percent",
            now=now,
            status=CheckStatus.FAIL if pool_saturated else CheckStatus.PASS,
            output=pool_output,
        )

        if any(c.status is CheckStatus.FAIL for c in checks.values()):
            overall = CheckStatus.FAIL
        elif any(c.status is CheckStatus.WARN for c in checks.values()):
            overall = CheckStatus.WARN
        else:
            overall = CheckStatus.PASS
        return ReadinessReport(status=overall, checks=checks)
