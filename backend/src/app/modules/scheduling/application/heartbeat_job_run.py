"""Renew an owned execution through a guarded transaction."""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar
from uuid import UUID

from app.modules.scheduling.ports.unit_of_work import SchedulingUnitOfWork
from app.shared_kernel.access import Access, System
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(frozen=True, kw_only=True)
class HeartbeatJobRunCommand:
    """The claimed run, its worker and the heartbeat instant."""

    run_id: UUID
    worker_id: str
    now: datetime


class HeartbeatJobRun(
    CommandHandler[SchedulingUnitOfWork, HeartbeatJobRunCommand, None]
):
    """Commit execution and worker liveness in one short transaction."""

    access: ClassVar[Access] = System()

    async def _handle(self, request: HeartbeatJobRunCommand, actor: Actor) -> None:
        async with self._uow as repos:
            await repos.recorder.heartbeat(
                request.run_id, request.worker_id, request.now
            )
            await repos.recorder.worker_heartbeat(request.worker_id, request.now)
            await self._uow.commit()
