"""Scheduler-owned job contributions without persistence access."""

from typing import TYPE_CHECKING

from app.modules.scheduling.adapters.cli.catalogue import JobBinding
from app.modules.scheduling.application.prune_job_runs import PruneJobRunsCommand
from app.shared_kernel.jobs import JobDefinition

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.modules.scheduling.application.prune_job_runs import PruneJobRuns
    from app.shared_kernel.actor import Actor


def prune_runs_job(
    command: Callable[[], PruneJobRuns], *, keep_per_job: int
) -> JobBinding:
    """Bind operational maintenance to a fresh command for every execution."""

    async def handler(actor: Actor) -> None:
        await command().handle(PruneJobRunsCommand(keep_per_job=keep_per_job), actor)

    return JobBinding(
        definition=JobDefinition(
            job_key="scheduling.prune_runs",
            schedule_key="scheduling.prune_schedule",
            needs_setup_complete=False,
        ),
        handler=handler,
    )
