"""Keep a running job's latest progress through a guarded transaction."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar
from uuid import UUID

from app.modules.scheduling.ports.unit_of_work import SchedulingUnitOfWork
from app.shared_kernel.access import Access, System
from app.shared_kernel.cqrs import CommandHandler
from app.shared_kernel.progress import ProgressSnapshot

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(frozen=True, kw_only=True)
class RecordJobRunProgressCommand:
    """The claimed run, its worker and the snapshot to keep."""

    run_id: UUID
    worker_id: str
    snapshot: ProgressSnapshot


class RecordJobRunProgress(
    CommandHandler[SchedulingUnitOfWork, RecordJobRunProgressCommand, None]
):
    """Commit a snapshot in its own short transaction, for the claimant only."""

    access: ClassVar[Access] = System()

    async def _handle(self, request: RecordJobRunProgressCommand, actor: Actor) -> None:
        async with self._uow as repos:
            await repos.recorder.record_progress(
                request.run_id, request.worker_id, request.snapshot
            )
            await self._uow.commit()
