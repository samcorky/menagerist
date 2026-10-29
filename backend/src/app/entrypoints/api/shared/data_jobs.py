"""Scheduled retention of deleted content, composed across modules."""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.entrypoints.api.shared.purge_deleted import (
    PurgeDeletedContentCommand,
    build_purge_deleted_content,
)
from app.platform.config.retention import get_retention_settings
from app.shared_kernel.jobs import JobContribution, JobDefinition, job

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@job(
    JobDefinition(
        job_key="data.purge_deleted",
        schedule_key="retention.purge_schedule",
        # A permanent deletion runs only on a schedule an administrator has set.
        run_now_allowed=False,
        title="Permanently remove old deleted items",
        description=(
            "Permanently removes items, connections and collections that have been "
            + "in Recently deleted for longer than the retention period."
        ),
    )
)
async def purge_deleted_content(actor: Actor) -> None:
    """Hard-delete everything deleted before the retention cutoff."""
    cutoff = datetime.now(UTC) - timedelta(days=get_retention_settings().deleted_days)
    await build_purge_deleted_content().handle(
        PurgeDeletedContentCommand(older_than=cutoff), actor
    )


def data_schedules() -> dict[str, str]:
    """Expose the deployment schedule to the settings-backed schedule source."""
    return {"retention.purge_schedule": get_retention_settings().purge_schedule}


def data_job_contribution() -> JobContribution:
    """The cross-module retention job and its deployment schedule."""
    return JobContribution.from_handlers(
        purge_deleted_content, schedules=data_schedules
    )
