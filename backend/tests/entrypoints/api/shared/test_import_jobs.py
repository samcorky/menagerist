"""The job that runs queued imports, composed across modules."""

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock

from app.entrypoints.api.shared import import_jobs
from app.modules.transfer.adapters.storage.in_memory_import_files import (
    InMemoryImportFileStore,
)
from app.modules.transfer.application.item_import import ImportItems
from app.modules.transfer.application.stored_imports import (
    ITEM_IMPORTS_JOB,
    RunQueuedImports,
)
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor
from app.shared_kernel.jobs import Lane, Overlap
from app.shared_kernel.progress import NULL_PROGRESS, SnapshotReporter

if TYPE_CHECKING:
    import pytest


def test_it_contributes_a_heavy_unscheduled_job_that_can_be_queued() -> None:
    """It starts when someone runs an import, and requests share one run."""
    [binding] = import_jobs.import_job_contribution().bindings()
    job = binding.definition
    assert job.job_key == ITEM_IMPORTS_JOB
    assert job.lane is Lane.HEAVY
    assert job.overlap is Overlap.COALESCE
    assert job.schedule_key is None
    assert job.title.strip()
    assert job.description.strip()


def test_the_drain_builds_each_import_over_its_owner() -> None:
    """The importer and reporter it is given work for any owner."""
    drain = import_jobs.build_run_queued_imports(Mock(), InMemoryImportFileStore())
    assert isinstance(drain, RunQueuedImports)
    owner = Actor(id=SYSTEM_ACTOR.id, roles=frozenset({"member"}))
    assert isinstance(drain._importer(owner, NULL_PROGRESS), ImportItems)
    assert isinstance(drain._reporter(owner.id), SnapshotReporter)


async def test_the_job_drains_the_queue_as_the_system(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It hands the queue to the drain and waits for it."""
    handle = AsyncMock()
    monkeypatch.setattr(import_jobs, "get_session_factory", Mock())
    monkeypatch.setattr(import_jobs, "import_file_store", Mock())
    monkeypatch.setattr(
        import_jobs,
        "build_run_queued_imports",
        Mock(return_value=Mock(handle=handle)),
    )
    await import_jobs.run_item_imports(SYSTEM_ACTOR)
    assert handle.await_args is not None
    assert handle.await_args.args[1] is SYSTEM_ACTOR
