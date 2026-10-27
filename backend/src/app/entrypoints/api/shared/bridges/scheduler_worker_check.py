"""Bridge scheduler liveness into warn-only system readiness diagnostics."""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import structlog

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.scheduling.adapters.persistence.job_run_reader import (
    SqlAlchemyJobRunReader,
)
from app.modules.scheduling.application.get_worker_status import (
    GetWorkerStatus,
    GetWorkerStatusQuery,
)
from app.modules.system.domain.readiness import CheckObservation, CheckStatus
from app.platform.config.scheduler import get_scheduler_settings
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = structlog.get_logger(__name__)


class SchedulerWorkerCheck:
    """Warn after the configured heartbeat timeout, including on check failure."""

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory
        self._timeout = get_scheduler_settings().worker_heartbeat_timeout_seconds

    async def run(self) -> dict[str, CheckObservation]:
        """Query through the scheduling application boundary in a short session."""
        now = datetime.now(UTC)
        try:
            async with self._factory() as session:
                alive = await GetWorkerStatus(
                    SqlAlchemyJobRunReader(session), get_access_guard()
                ).handle(
                    GetWorkerStatusQuery(since=now - timedelta(seconds=self._timeout)),
                    SYSTEM_ACTOR,
                )
            output = (
                None
                if alive
                else f"No worker heartbeat in the last {self._timeout} seconds."
            )
            observed_value: float | str = int(alive)
        except Exception:
            logger.exception("worker readiness check failed")
            alive = False
            observed_value = "unknown"
            output = "Worker status could not be checked."
        return {
            "scheduler:worker": CheckObservation(
                component_type="component",
                observed_value=observed_value,
                observed_unit="boolean",
                status=CheckStatus.PASS if alive else CheckStatus.WARN,
                time=now,
                output=output,
            )
        }
