"""Background CSV imports, composed across modules.

An import runs as its owner, over the same preset and graph targets as a request
of theirs, so the job is composed here rather than in the transfer module.
"""

from typing import TYPE_CHECKING

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.entrypoints.api.shared.bridges.import_actors import build_import_actors
from app.entrypoints.api.shared.bridges.transfer_targets import (
    GraphPackTarget,
    PresetPackTarget,
    build_graph_stores,
    build_preset_stores,
)
from app.entrypoints.api.shared.progress import make_reporter
from app.modules.transfer.adapters.persistence.unit_of_work import create_transfer_uow
from app.modules.transfer.adapters.scheduling.import_progress import (
    ItemImportProgressSink,
)
from app.modules.transfer.adapters.storage.local_import_files import import_file_store
from app.modules.transfer.application.item_import import ImportItems
from app.modules.transfer.application.stored_imports import (
    ITEM_IMPORTS_JOB,
    RecordItemImportProgress,
    RunQueuedImports,
    RunQueuedImportsCommand,
)
from app.platform.database import get_session_factory
from app.shared_kernel.jobs import JobContribution, JobDefinition, Lane, job
from app.shared_kernel.progress import NULL_PROGRESS

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.transfer.ports.import_file_store import ImportFileStore
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.progress import ProgressReporter


def build_run_queued_imports(
    session_factory: async_sessionmaker[AsyncSession],
    store: ImportFileStore,
) -> RunQueuedImports:
    """The drain, with each import built over its owner's targets."""
    guard = get_access_guard()

    def importer(actor: Actor, progress: ProgressReporter) -> ImportItems:
        return ImportItems(
            create_transfer_uow(session_factory),
            guard,
            PresetPackTarget(build_preset_stores(session_factory), actor),
            GraphPackTarget(build_graph_stores(session_factory), actor),
            progress,
        )

    def reporter(import_id: uuid.UUID) -> ProgressReporter:
        return make_reporter(
            ItemImportProgressSink(
                lambda: RecordItemImportProgress(
                    create_transfer_uow(session_factory), guard
                ),
                import_id,
            )
        )

    return RunQueuedImports(
        lambda: create_transfer_uow(session_factory),
        guard,
        store,
        build_import_actors(session_factory),
        importer,
        reporter,
    )


@job(
    JobDefinition(
        job_key=ITEM_IMPORTS_JOB,
        lane=Lane.HEAVY,
        title="Run waiting imports",
        description=(
            "Imports the CSV files people have queued, one at a time, taking turns "
            + "between people. It starts by itself when someone runs an import."
        ),
    )
)
async def run_item_imports(
    actor: Actor, progress: ProgressReporter = NULL_PROGRESS
) -> None:
    """Run every queued import until none is waiting."""
    await build_run_queued_imports(get_session_factory(), import_file_store()).handle(
        RunQueuedImportsCommand(), actor
    )


def import_job_contribution() -> JobContribution:
    """The job that runs queued imports."""
    return JobContribution.from_handlers(run_item_imports)
