"""Maintain idle worker liveness and fence expired executions."""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

from app.modules.scheduling.ports.unit_of_work import SchedulingUnitOfWork
from app.shared_kernel.access import Access, System
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(frozen=True, kw_only=True)
class MaintainWorkerCommand:
    """The worker heartbeat and the execution expiry boundary."""

    worker_id: str
    now: datetime
    older_than: datetime


class MaintainWorker(CommandHandler[SchedulingUnitOfWork, MaintainWorkerCommand, int]):
    """Reap stale work and record worker liveness in one short transaction."""

    access: ClassVar[Access] = System()

    async def _handle(self, request: MaintainWorkerCommand, actor: Actor) -> int:
        async with self._uow as repos:
            count = await repos.recorder.reap_abandoned(request.older_than, request.now)
            await repos.recorder.worker_heartbeat(request.worker_id, request.now)
            await self._uow.commit()
        return count
