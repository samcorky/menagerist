"""The scheduler's own housekeeping job, composed from its use case."""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.modules.scheduling.adapters.persistence.unit_of_work import (
    create_scheduling_uow,
)
from app.modules.scheduling.application.prune_job_runs import (
    PruneJobRuns,
    PruneJobRunsCommand,
)
from app.modules.scheduling.application.setting_keys import RUN_HISTORY_PER_JOB
from app.platform.database import get_session_factory
from app.shared_kernel.jobs import JobContribution, JobDefinition, job

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

# Each worker start adds a heartbeat row under a new id; nothing else removes it.
_WORKER_HEARTBEAT_RETENTION = timedelta(days=7)


@job(
    JobDefinition(
        job_key="scheduling.prune_runs",
        schedule_key="scheduling.prune_schedule",
        needs_setup_complete=False,
        title="Tidy task history",
        description=(
            "Forgets the oldest results, and workers that stopped a week ago, "
            + "so this list stays short."
        ),
    )
)
async def prune_job_runs(actor: Actor) -> None:
    """Apply the current run quota and forget workers that have gone quiet."""
    from app.entrypoints.api.shared.access_guard import get_access_guard
    from app.entrypoints.api.shared.settings_reader import get_settings_reader

    command = PruneJobRunsCommand(
        keep_per_job=await get_settings_reader().get(RUN_HISTORY_PER_JOB),
        worker_heartbeats_before=datetime.now(UTC) - _WORKER_HEARTBEAT_RETENTION,
    )
    await PruneJobRuns(
        create_scheduling_uow(get_session_factory()), get_access_guard()
    ).handle(command, actor)


def scheduling_schedules() -> dict[str, str]:
    """The default schedule; an administrator can override it in settings."""
    return {"scheduling.prune_schedule": "0 4 * * *"}


def scheduling_job_contribution() -> JobContribution:
    """The scheduler's job and its default schedule."""
    return JobContribution.from_handlers(prune_job_runs, schedules=scheduling_schedules)
