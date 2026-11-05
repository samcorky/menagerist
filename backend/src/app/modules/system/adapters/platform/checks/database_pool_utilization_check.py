from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from sqlalchemy.pool import QueuePool

from app.modules.system.adapters.platform.checks._util import observation
from app.modules.system.domain.readiness import CheckObservation, CheckStatus
from app.platform.config import get_database_settings
from app.platform.database import get_engine

if TYPE_CHECKING:
    from collections.abc import Mapping


class DatabasePoolUtilizationCheck:
    """Reports how much of the connection pool is currently checked out.

    Measured against the pooled and overflow connections together, so `fail` means a
    request would have to wait for one. Pure in-process introspection, no I/O.
    """

    async def run(self) -> Mapping[str, CheckObservation]:
        """Inspect the connection pool and report its utilisation."""
        now = datetime.now(UTC)
        settings = get_database_settings()
        # A process may hold the pooled connections plus the overflow ones.
        capacity = settings.connections_per_process
        # Warn once the overflow is half used: the pool is regularly outgrowing its
        # base size.
        warn_at = settings.pool_size + settings.max_overflow // 2
        pool_obj = cast(QueuePool, get_engine().pool)
        checkedout = pool_obj.checkedout()
        utilization = round(checkedout / capacity * 100, 2)
        status = CheckStatus.PASS
        output: str | None = None
        if checkedout >= capacity:
            status = CheckStatus.FAIL
            output = f"{checkedout}/{capacity} connections checked out, 0 available"
        elif checkedout >= warn_at:
            status = CheckStatus.WARN
            output = f"{checkedout}/{capacity} connections checked out"
        return {
            "database:poolUtilization": observation(
                utilization, "percent", now=now, status=status, output=output
            )
        }
