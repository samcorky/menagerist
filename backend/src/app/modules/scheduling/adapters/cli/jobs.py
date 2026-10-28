"""Scheduler-owned job contributions without persistence access."""

from typing import TYPE_CHECKING

from app.modules.scheduling.application.prune_job_runs import PruneJobRunsCommand
from app.shared_kernel.jobs import JobBinding, JobDefinition

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.modules.scheduling.application.prune_job_runs import PruneJobRuns
    from app.shared_kernel.actor import Actor


def prune_runs_job(
    command: Callable[[], PruneJobRuns],
    *,
    keep_per_job: Callable[[], Awaitable[int]],
) -> JobBinding:
    """Bind operational maintenance to a fresh command and the current quota."""

    async def handler(actor: Actor) -> None:
        quota = PruneJobRunsCommand(keep_per_job=await keep_per_job())
        await command().handle(quota, actor)

    return JobBinding(
        definition=JobDefinition(
            job_key="scheduling.prune_runs",
            schedule_key="scheduling.prune_schedule",
            needs_setup_complete=False,
            title="Tidy task history",
            description="Forgets the oldest results so this list stays short.",
        ),
        handler=handler,
    )
