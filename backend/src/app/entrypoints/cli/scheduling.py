"""Compose scheduler execution through application use cases."""

from typing import TYPE_CHECKING

from app.modules.identity.adapters.persistence.unit_of_work import build_identity_repos
from app.modules.identity.application.get_setup_status import (
    GetSetupStatus,
    GetSetupStatusQuery,
)
from app.modules.scheduling.adapters.cli.execution import JobExecutor
from app.modules.scheduling.adapters.persistence.unit_of_work import (
    create_scheduling_uow,
)
from app.modules.scheduling.adapters.platform.restore_guard import (
    SqlAlchemyRestoreGuard,
)
from app.modules.scheduling.application.check_job_execution import CheckJobExecution
from app.modules.scheduling.application.finish_job_run import FinishJobRun
from app.modules.scheduling.application.heartbeat_job_run import HeartbeatJobRun
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.shared_kernel.access_guard import AccessGuard


class SchedulingSetupState:
    """Bridge the scheduler's setup port to identity's existing status query."""

    def __init__(
        self, factory: async_sessionmaker[AsyncSession], guard: AccessGuard
    ) -> None:
        self._factory = factory
        self._guard = guard

    async def is_complete(self) -> bool:
        """Use a short read-only session for each eligibility check."""
        async with self._factory() as session:
            status = GetSetupStatus(build_identity_repos(session), self._guard)
            return not await status.handle(GetSetupStatusQuery(), SYSTEM_ACTOR)


def build_job_executor(
    factory: async_sessionmaker[AsyncSession], guard: AccessGuard
) -> JobExecutor:
    """Give each recording command its own transaction and a real access guard."""
    return JobExecutor(
        lambda: HeartbeatJobRun(create_scheduling_uow(factory), guard),
        lambda: FinishJobRun(create_scheduling_uow(factory), guard),
        CheckJobExecution(SchedulingSetupState(factory, guard), guard),
        SqlAlchemyRestoreGuard(factory),
    )
