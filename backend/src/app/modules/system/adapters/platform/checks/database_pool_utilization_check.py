from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, cast

from sqlalchemy.pool import QueuePool

from app.modules.system.adapters.platform.checks._util import observation
from app.modules.system.domain.readiness import CheckObservation, CheckStatus
from app.platform.connection_budget import MAX_OVERFLOW, POOL_SIZE
from app.platform.database import get_engine

if TYPE_CHECKING:
    from collections.abc import Mapping


# A process may hold the pooled connections plus the overflow ones.
_CAPACITY: Final = POOL_SIZE + MAX_OVERFLOW
# Warn once the overflow is half used: the pool is regularly outgrowing its base size.
_WARN_AT: Final = POOL_SIZE + MAX_OVERFLOW // 2


class DatabasePoolUtilizationCheck:
    """Reports how much of the connection pool is currently checked out.

    Measured against the pooled and overflow connections together, so `fail` means a
    request would have to wait for one. Pure in-process introspection, no I/O.
    """

    async def run(self) -> Mapping[str, CheckObservation]:
        """Inspect the connection pool and report its utilisation."""
        now = datetime.now(UTC)
        pool_obj = cast(QueuePool, get_engine().pool)
        checkedout = pool_obj.checkedout()
        utilization = round(checkedout / _CAPACITY * 100, 2)
        status = CheckStatus.PASS
        output: str | None = None
        if checkedout >= _CAPACITY:
            status = CheckStatus.FAIL
            output = f"{checkedout}/{_CAPACITY} connections checked out, 0 available"
        elif checkedout >= _WARN_AT:
            status = CheckStatus.WARN
            output = f"{checkedout}/{_CAPACITY} connections checked out"
        return {
            "database:poolUtilization": observation(
                utilization, "percent", now=now, status=status, output=output
            )
        }
