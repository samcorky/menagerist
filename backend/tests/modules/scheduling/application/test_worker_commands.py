"""Worker bookkeeping stays behind guarded application commands."""

from datetime import UTC, datetime, timedelta

import pytest

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.scheduling.adapters.persistence.in_memory_store import (
    InMemorySchedulingStore,
)
from app.modules.scheduling.adapters.persistence.unit_of_work import (
    build_in_memory_scheduling_repos,
    create_in_memory_scheduling_uow,
)
from app.modules.scheduling.application.claim_job_run import (
    ClaimJobRun,
    ClaimJobRunCommand,
)
from app.modules.scheduling.application.get_job_run import GetJobRun, GetJobRunQuery
from app.modules.scheduling.application.maintain_worker import (
    MaintainWorker,
    MaintainWorkerCommand,
)
from app.modules.scheduling.domain.job_run import JobRun, RunStatus
from app.shared_kernel.actor import ANONYMOUS_ACTOR, SYSTEM_ACTOR
from app.shared_kernel.errors import ForbiddenError
from app.shared_kernel.jobs import Lane

NOW = datetime(2026, 10, 27, 12, tzinfo=UTC)


async def test_claim_and_maintenance_commit_their_own_transactions() -> None:
    """Claims, reaping and idle worker liveness are separate short transactions."""
    store = InMemorySchedulingStore()
    repos = build_in_memory_scheduling_repos(store)
    accepted = await repos.queue.enqueue(JobRun.create(job_key="x", scheduled_for=NOW))
    uow = create_in_memory_scheduling_uow(store)
    claimed = await ClaimJobRun(uow, get_access_guard()).handle(
        ClaimJobRunCommand(
            lanes=(Lane.DEFAULT,), worker_id="one", now=NOW, run_id=accepted.id
        ),
        SYSTEM_ACTOR,
    )
    assert claimed is not None
    assert claimed.id == accepted.id
    assert uow.committed
    maintenance = create_in_memory_scheduling_uow(store)
    count = await MaintainWorker(maintenance, get_access_guard()).handle(
        MaintainWorkerCommand(
            worker_id="idle",
            now=NOW + timedelta(minutes=3),
            older_than=NOW + timedelta(minutes=1),
        ),
        SYSTEM_ACTOR,
    )
    assert count == 1
    assert maintenance.committed
    assert await repos.reader.worker_alive(NOW + timedelta(minutes=3))
    result = await GetJobRun(repos.reader, get_access_guard()).handle(
        GetJobRunQuery(run_id=accepted.id), SYSTEM_ACTOR
    )
    assert result.status is RunStatus.ABANDONED
    empty = create_in_memory_scheduling_uow(store)
    assert (
        await ClaimJobRun(empty, get_access_guard()).handle(
            ClaimJobRunCommand(lanes=tuple(Lane), worker_id="two", now=NOW),
            SYSTEM_ACTOR,
        )
        is None
    )
    assert empty.committed


async def test_worker_commands_and_run_query_refuse_anonymous_access() -> None:
    """A caller cannot claim or maintain worker state without the system stance."""
    store = InMemorySchedulingStore()
    uow = create_in_memory_scheduling_uow(store)
    run = JobRun.create(job_key="x", scheduled_for=NOW)
    with pytest.raises(ForbiddenError):
        await ClaimJobRun(uow, get_access_guard()).handle(
            ClaimJobRunCommand(lanes=tuple(Lane), worker_id="x", now=NOW),
            ANONYMOUS_ACTOR,
        )
    with pytest.raises(ForbiddenError):
        await MaintainWorker(uow, get_access_guard()).handle(
            MaintainWorkerCommand(worker_id="x", now=NOW, older_than=NOW),
            ANONYMOUS_ACTOR,
        )
    with pytest.raises(ForbiddenError):
        await GetJobRun(
            build_in_memory_scheduling_repos(store).reader, get_access_guard()
        ).handle(GetJobRunQuery(run_id=run.id), ANONYMOUS_ACTOR)
    assert not uow.committed
