"""The scheduling repository bundle and its shared transaction boundary."""

from dataclasses import dataclass

from app.modules.scheduling.ports.job_run_queue import JobRunQueue
from app.modules.scheduling.ports.job_run_reader import JobRunReader
from app.modules.scheduling.ports.job_run_recorder import JobRunRecorder
from app.modules.scheduling.ports.schedule_cursor_store import ScheduleCursorStore
from app.shared_kernel.unit_of_work import UnitOfWork


@dataclass(kw_only=True)
class SchedulingRepos:
    """Repositories participating in one scheduling transaction."""

    queue: JobRunQueue
    reader: JobRunReader
    recorder: JobRunRecorder
    cursors: ScheduleCursorStore


SchedulingUnitOfWork = UnitOfWork[SchedulingRepos]
