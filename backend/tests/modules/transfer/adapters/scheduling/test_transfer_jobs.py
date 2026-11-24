"""The transfer module's clean-up job, and the sink that shows import progress."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, Mock

from app.modules.transfer.adapters.scheduling import jobs as transfer_jobs
from app.modules.transfer.adapters.scheduling.import_progress import (
    ItemImportProgressSink,
)
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.progress import ProgressSnapshot

if TYPE_CHECKING:
    import pytest

SNAPSHOT = ProgressSnapshot(phases=(), message=None, percent=5, outcome="running")


def test_it_contributes_the_scheduled_clean_up() -> None:
    """The job describes itself and reads its schedule from the settings."""
    [binding] = transfer_jobs.transfer_job_contribution().bindings()
    job = binding.definition
    assert job.job_key == "transfer.prune_imports"
    assert job.schedule_key == "transfer.prune_imports_schedule"
    assert job.title.strip()
    assert job.description.strip()
    schedules = transfer_jobs.transfer_schedules()
    assert schedules == {"transfer.prune_imports_schedule": "15 * * * *"}


async def test_the_clean_up_removes_what_expired_by_now(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It runs as the system, with the current time as the cut-off."""
    handle = AsyncMock()
    monkeypatch.setattr(transfer_jobs, "create_transfer_uow", Mock())
    monkeypatch.setattr(transfer_jobs, "get_session_factory", Mock())
    monkeypatch.setattr(transfer_jobs, "import_file_store", Mock())
    monkeypatch.setattr(
        transfer_jobs, "PruneItemImports", Mock(return_value=Mock(handle=handle))
    )
    before = datetime.now(UTC)
    await transfer_jobs.prune_item_imports(SYSTEM_ACTOR)
    assert handle.await_args is not None
    [command, actor] = handle.await_args.args
    assert actor is SYSTEM_ACTOR
    assert before <= command.before <= datetime.now(UTC)


async def test_the_sink_records_each_snapshot_on_the_import() -> None:
    """Each write is its own short command, as the system."""
    seen: list[Any] = []

    class Record:
        async def handle(self, command: Any, actor: Any) -> None:  # noqa: ANN401
            seen.append((command.import_id, command.snapshot, actor))

    import_id = uuid.uuid7()
    sink = ItemImportProgressSink(Record, import_id)  # type: ignore[arg-type]
    await sink.write(SNAPSHOT)
    assert seen == [(import_id, SNAPSHOT, SYSTEM_ACTOR)]
