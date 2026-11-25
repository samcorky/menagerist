"""Scheduled clean-up of uploaded import files."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.modules.transfer.adapters.persistence.unit_of_work import create_transfer_uow
from app.modules.transfer.adapters.storage.local_import_files import import_file_store
from app.modules.transfer.application.stored_imports import (
    PruneItemImports,
    PruneItemImportsCommand,
)
from app.platform.config.transfer import get_transfer_settings
from app.platform.database import get_session_factory
from app.shared_kernel.jobs import JobContribution, JobDefinition, job
from app.shared_kernel.progress import NULL_PROGRESS

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.progress import ProgressReporter


@job(
    JobDefinition(
        job_key="transfer.prune_imports",
        schedule_key="transfer.prune_imports_schedule",
        title="Clear old uploaded imports",
        description=(
            "Removes uploaded CSV files never imported, and the results of "
            + "finished imports, once they are older than the keeping time."
        ),
    )
)
async def prune_item_imports(
    actor: Actor, progress: ProgressReporter = NULL_PROGRESS
) -> None:
    """Remove the imports that have expired."""
    from app.entrypoints.api.shared.access_guard import get_access_guard

    await PruneItemImports(
        create_transfer_uow(get_session_factory()),
        get_access_guard(),
        import_file_store(),
    ).handle(PruneItemImportsCommand(before=datetime.now(UTC)), actor)


def transfer_schedules() -> dict[str, str]:
    """Expose the deployment schedule to the settings-backed schedule source."""
    return {
        "transfer.prune_imports_schedule": (
            get_transfer_settings().prune_imports_schedule
        )
    }


def transfer_job_contribution() -> JobContribution:
    """The transfer module's clean-up job and its schedule."""
    return JobContribution.from_handlers(
        prune_item_imports, schedules=transfer_schedules
    )
