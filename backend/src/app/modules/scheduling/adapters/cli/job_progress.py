"""Write a job's progress to its run row, so the interface can show it."""

from typing import TYPE_CHECKING

from app.modules.scheduling.application.record_job_run_progress import (
    RecordJobRunProgressCommand,
)
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    from collections.abc import Callable
    from uuid import UUID

    from app.modules.scheduling.application.record_job_run_progress import (
        RecordJobRunProgress,
    )
    from app.shared_kernel.progress import ProgressSnapshot


class JobRunProgressSink:
    """Each snapshot is its own short transaction, fenced to the run's claimant."""

    def __init__(
        self,
        record: Callable[[], RecordJobRunProgress],
        run_id: UUID,
        worker_id: str,
    ) -> None:
        self._record = record
        self._run_id = run_id
        self._worker_id = worker_id

    async def write(self, snapshot: ProgressSnapshot) -> None:
        """Keep the snapshot; a lost claim raises and the reporter swallows it."""
        await self._record().handle(
            RecordJobRunProgressCommand(
                run_id=self._run_id, worker_id=self._worker_id, snapshot=snapshot
            ),
            SYSTEM_ACTOR,
        )
