"""Execution state changes are guarded application transactions."""

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
from app.modules.scheduling.adapters.platform.in_memory_setup_state import (
    InMemorySetupState,
)
from app.modules.scheduling.application.check_job_execution import (
    CheckJobExecution,
    CheckJobExecutionQuery,
)
from app.modules.scheduling.application.finish_job_run import (
    FinishJobRun,
    FinishJobRunCommand,
)
from app.modules.scheduling.application.heartbeat_job_run import (
    HeartbeatJobRun,
    HeartbeatJobRunCommand,
)
from app.modules.scheduling.domain.errors import LostClaimError
from app.modules.scheduling.domain.job_run import JobRun, RunStatus
from app.shared_kernel.actor import ANONYMOUS_ACTOR, SYSTEM_ACTOR
from app.shared_kernel.errors import ForbiddenError
from app.shared_kernel.jobs import JobDefinition, Lane

NOW = datetime(2026, 10, 27, 12, tzinfo=UTC)


async def test_execution_commands_commit_heartbeat_and_terminal_outcome() -> None:
    """Commands own recorder access and commit each short transaction."""
    store = InMemorySchedulingStore()
    repos = build_in_memory_scheduling_repos(store)
    accepted = await repos.queue.enqueue(JobRun.create(job_key="x", scheduled_for=NOW))
    await repos.queue.claim([Lane.DEFAULT], "worker", NOW)
    heartbeat_uow = create_in_memory_scheduling_uow(store)
    await HeartbeatJobRun(heartbeat_uow, get_access_guard()).handle(
        HeartbeatJobRunCommand(
            run_id=accepted.id, worker_id="worker", now=NOW + timedelta(seconds=1)
        ),
        SYSTEM_ACTOR,
    )
    assert heartbeat_uow.committed
    assert store.get(accepted.id).heartbeat_at == NOW + timedelta(seconds=1)
    assert await repos.reader.worker_alive(NOW + timedelta(seconds=1))
    finish_uow = create_in_memory_scheduling_uow(store)
    await FinishJobRun(finish_uow, get_access_guard()).handle(
        FinishJobRunCommand(
            run_id=accepted.id,
            worker_id="worker",
            status=RunStatus.FAILED,
            now=NOW + timedelta(seconds=2),
            error="failure",
        ),
        SYSTEM_ACTOR,
    )
    assert finish_uow.committed
    stored = store.get(accepted.id)
    assert stored.status is RunStatus.FAILED
    assert stored.error == "failure"


async def test_wrong_owner_cannot_commit_an_execution_command() -> None:
    """Ownership checks remain in the domain and roll back the command."""
    store = InMemorySchedulingStore()
    repos = build_in_memory_scheduling_repos(store)
    accepted = await repos.queue.enqueue(JobRun.create(job_key="x", scheduled_for=NOW))
    await repos.queue.claim([Lane.DEFAULT], "worker", NOW)
    uow = create_in_memory_scheduling_uow(store)
    with pytest.raises(LostClaimError):
        await HeartbeatJobRun(uow, get_access_guard()).handle(
            HeartbeatJobRunCommand(run_id=accepted.id, worker_id="wrong", now=NOW),
            SYSTEM_ACTOR,
        )
    assert not uow.committed
    assert uow.rolled_back
    with pytest.raises(LostClaimError):
        await FinishJobRun(uow, get_access_guard()).handle(
            FinishJobRunCommand(
                run_id=accepted.id,
                worker_id="wrong",
                status=RunStatus.SUCCEEDED,
                now=NOW,
            ),
            SYSTEM_ACTOR,
        )
    assert not uow.committed


async def test_execution_use_cases_are_system_only() -> None:
    """Neither recording nor eligibility may be driven by an anonymous actor."""
    run = JobRun.create(job_key="x", scheduled_for=NOW)
    uow = create_in_memory_scheduling_uow(InMemorySchedulingStore())
    with pytest.raises(ForbiddenError):
        await HeartbeatJobRun(uow, get_access_guard()).handle(
            HeartbeatJobRunCommand(run_id=run.id, worker_id="worker", now=NOW),
            ANONYMOUS_ACTOR,
        )
    with pytest.raises(ForbiddenError):
        await FinishJobRun(uow, get_access_guard()).handle(
            FinishJobRunCommand(
                run_id=run.id, worker_id="worker", status=RunStatus.SUCCEEDED, now=NOW
            ),
            ANONYMOUS_ACTOR,
        )
    with pytest.raises(ForbiddenError):
        await CheckJobExecution(InMemorySetupState(), get_access_guard()).handle(
            CheckJobExecutionQuery(
                job=JobDefinition(job_key="x"), restore_available=True
            ),
            ANONYMOUS_ACTOR,
        )
    assert not uow.committed


@pytest.mark.parametrize(
    ("requires_setup", "complete", "available", "reason"),
    [
        (True, True, True, None),
        (True, False, True, "setup_incomplete"),
        (False, False, True, None),
        (True, False, False, "restore_in_progress"),
    ],
)
async def test_eligibility_query_applies_setup_and_restore_policy(
    requires_setup: bool, complete: bool, available: bool, reason: str | None
) -> None:
    """The adapter receives an eligibility result instead of applying domain policy."""
    result = await CheckJobExecution(
        InMemorySetupState(complete=complete), get_access_guard()
    ).handle(
        CheckJobExecutionQuery(
            job=JobDefinition(job_key="x", needs_setup_complete=requires_setup),
            restore_available=available,
        ),
        SYSTEM_ACTOR,
    )
    assert result == reason
