from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from sqlalchemy.pool import QueuePool

from app.modules.system.adapters.platform.checks._util import observation
from app.modules.system.domain.readiness import CheckObservation, CheckStatus
from app.platform.database import get_engine

if TYPE_CHECKING:
    from collections.abc import Mapping


class DatabasePoolUtilizationCheck:
    """Reports how much of the connection pool is currently checked out.

    Pure in-process introspection, no I/O.
    """

    async def run(self) -> Mapping[str, CheckObservation]:
        """Inspect the connection pool and report its utilisation."""
        now = datetime.now(UTC)
        pool_obj = cast(QueuePool, get_engine().pool)
        checkedout = pool_obj.checkedout()
        pool_size = pool_obj.size()
        pool_saturated = 0 < pool_size <= checkedout
        utilization = round(checkedout / pool_size * 100, 2) if pool_size > 0 else 0.0
        output: str | None = (
            f"{checkedout}/{pool_size} connections checked out, 0 available"
            if pool_saturated
            else None
        )
        return {
            "database:poolUtilization": observation(
                utilization,
                "percent",
                now=now,
                status=CheckStatus.FAIL if pool_saturated else CheckStatus.PASS,
                output=output,
            )
        }
