"""Administrative run-now and read-only job queries."""

from datetime import UTC, datetime, timedelta
from uuid import uuid7

import pytest

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.scheduling.adapters.persistence.in_memory_store import (
    InMemorySchedulingStore,
)
from app.modules.scheduling.adapters.persistence.unit_of_work import (
    build_in_memory_scheduling_repos,
    create_in_memory_scheduling_uow,
)
from app.modules.scheduling.adapters.platform.cron_evaluator import (
    CronScheduleEvaluator,
)
from app.modules.scheduling.adapters.platform.in_memory_schedule_source import (
    InMemoryScheduleSource,
)
from app.modules.scheduling.application.get_job_history import (
    GetJobHistory,
    GetJobHistoryQuery,
)
from app.modules.scheduling.application.list_jobs import ListJobs, ListJobsQuery
from app.modules.scheduling.application.permissions import SchedulingPermission
from app.modules.scheduling.application.run_job_now import RunJobNow, RunJobNowCommand
from app.modules.scheduling.domain.errors import RunNowNotAllowedError, UnknownJobError
from app.modules.scheduling.domain.registry import JobRegistry
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor
from app.shared_kernel.errors import ForbiddenError, ValidationError
from app.shared_kernel.jobs import JobDefinition, Lane, Overlap

NOW = datetime(2026, 10, 26, 3, tzinfo=UTC)
ADMIN = Actor(id=uuid7(), roles=frozenset({"admin"}))
MEMBER = Actor(id=uuid7(), roles=frozenset({"member"}))


async def test_run_now_is_idempotent_and_commits_requester_and_policy() -> None:
    """Repeated manual requests reuse active work even when its policy is queue."""
    store = InMemorySchedulingStore()
    registry = JobRegistry(
        [JobDefinition(job_key="backup.create", lane=Lane.HEAVY, overlap=Overlap.QUEUE)]
    )
    uow = create_in_memory_scheduling_uow(store)
    command = RunJobNowCommand(job_key="backup.create", now=NOW)
    first = await RunJobNow(uow, get_access_guard(), registry).handle(command, ADMIN)
    second = await RunJobNow(
        create_in_memory_scheduling_uow(store), get_access_guard(), registry
    ).handle(command, ADMIN)
    assert first.id == second.id
    assert first.requested_by == ADMIN.id
    assert first.lane is Lane.HEAVY
    assert first.overlap is Overlap.QUEUE
    assert first.deduplication_key is None
    assert uow.committed


async def test_system_run_now_has_no_human_requester() -> None:
    """Internal execution does not store the system sentinel as a user reference."""
    store = InMemorySchedulingStore()
    run = await RunJobNow(
        create_in_memory_scheduling_uow(store),
        get_access_guard(),
        JobRegistry([JobDefinition(job_key="x")]),
    ).handle(RunJobNowCommand(job_key="x", now=NOW), SYSTEM_ACTOR)
    assert run.requested_by is None


@pytest.mark.parametrize(
    ("key", "error"), [("missing", UnknownJobError), ("blocked", RunNowNotAllowedError)]
)
async def test_unknown_and_disallowed_jobs_do_not_commit(
    key: str, error: type[Exception]
) -> None:
    """The registry enforces manual-run availability before opening a transaction."""
    store = InMemorySchedulingStore()
    uow = create_in_memory_scheduling_uow(store)
    case = RunJobNow(
        uow,
        get_access_guard(),
        JobRegistry([JobDefinition(job_key="blocked", run_now_allowed=False)]),
    )
    with pytest.raises(error):
        await case.handle(RunJobNowCommand(job_key=key, now=NOW), ADMIN)
    assert not uow.committed
    assert not store.runs


async def test_members_cannot_submit_jobs_or_read_history() -> None:
    """Scheduling permissions are admin-only and checked before any work."""
    store = InMemorySchedulingStore()
    registry = JobRegistry([JobDefinition(job_key="x")])
    uow = create_in_memory_scheduling_uow(store)
    with pytest.raises(ForbiddenError):
        await RunJobNow(uow, get_access_guard(), registry).handle(
            RunJobNowCommand(job_key="x", now=NOW), MEMBER
        )
    reader = build_in_memory_scheduling_repos(store).reader
    with pytest.raises(ForbiddenError):
        await GetJobHistory(reader, get_access_guard(), registry).handle(
            GetJobHistoryQuery(job_key="x"), MEMBER
        )
    assert not uow.committed
    assert SchedulingPermission.RUN.implied() == frozenset({SchedulingPermission.READ})
    assert not SchedulingPermission.READ.implied()


async def test_status_lists_enabled_disabled_and_manual_jobs_without_writes() -> None:
    """Status includes the next local fire and active work without advancing cursors."""
    store = InMemorySchedulingStore()
    registry = JobRegistry(
        [
            JobDefinition(job_key="enabled", schedule_key="enabled"),
            JobDefinition(job_key="disabled", schedule_key="disabled"),
            JobDefinition(job_key="manual"),
        ]
    )
    sources = InMemoryScheduleSource({"enabled": "0 3 * * *", "disabled": ""})
    case = ListJobs(
        build_in_memory_scheduling_repos(store).reader,
        get_access_guard(),
        registry,
        sources,
        CronScheduleEvaluator(),
    )
    statuses = await case.handle(ListJobsQuery(now=NOW, timezone="UTC"), ADMIN)
    assert [status.definition.job_key for status in statuses] == [
        "enabled",
        "disabled",
        "manual",
    ]
    assert statuses[0].next_run_at == NOW + timedelta(days=1)
    assert statuses[0].expression == "0 3 * * *"
    assert statuses[1].next_run_at is None
    assert statuses[2].expression is None
    assert not store.cursors
    assert not store.runs
    await RunJobNow(
        create_in_memory_scheduling_uow(store), get_access_guard(), registry
    ).handle(RunJobNowCommand(job_key="enabled", now=NOW), ADMIN)
    statuses = await case.handle(ListJobsQuery(now=NOW, timezone="UTC"), ADMIN)
    assert statuses[0].active_run is not None
    with pytest.raises(ForbiddenError):
        await case.handle(ListJobsQuery(now=NOW, timezone="UTC"), MEMBER)


async def test_history_is_scoped_to_registered_job_and_limit() -> None:
    """History queries reject unknown keys and apply their requested limit."""
    store = InMemorySchedulingStore()
    registry = JobRegistry([JobDefinition(job_key="x")])
    await RunJobNow(
        create_in_memory_scheduling_uow(store), get_access_guard(), registry
    ).handle(RunJobNowCommand(job_key="x", now=NOW), ADMIN)
    query = GetJobHistory(
        build_in_memory_scheduling_repos(store).reader, get_access_guard(), registry
    )
    assert len(await query.handle(GetJobHistoryQuery(job_key="x", limit=1), ADMIN)) == 1
    with pytest.raises(UnknownJobError):
        await query.handle(GetJobHistoryQuery(job_key="missing"), ADMIN)
    with pytest.raises(ValidationError):
        GetJobHistoryQuery(job_key="x", limit=0)
