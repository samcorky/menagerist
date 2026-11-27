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
    JobRunSort,
)
from app.modules.scheduling.application.list_jobs import (
    JobSort,
    ListJobs,
    ListJobsQuery,
)
from app.modules.scheduling.application.permissions import SchedulingPermission
from app.modules.scheduling.application.run_job_now import RunJobNow, RunJobNowCommand
from app.modules.scheduling.domain.errors import RunNowNotAllowedError, UnknownJobError
from app.modules.scheduling.domain.registry import JobRegistry
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor
from app.shared_kernel.errors import ForbiddenError, ValidationError
from app.shared_kernel.jobs import JobDefinition, Lane, Overlap
from app.shared_kernel.paging import SortOrder

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
            JobDefinition(job_key="enabled", schedule_key="enabled", title="A enabled"),
            JobDefinition(job_key="disabled", schedule_key="disabled", title="B off"),
            JobDefinition(job_key="manual", title="C manual"),
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
    statuses = (await case.handle(_query(), ADMIN)).items
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
    statuses = (await case.handle(_query(), ADMIN)).items
    assert statuses[0].active_run is not None
    with pytest.raises(ForbiddenError):
        await case.handle(_query(), MEMBER)


def _query(**fields: object) -> ListJobsQuery:
    return ListJobsQuery(now=NOW, timezone="UTC", **fields)  # type: ignore[arg-type]


async def _listing(*definitions: JobDefinition, schedules: dict[str, str]) -> ListJobs:
    store = InMemorySchedulingStore()
    return ListJobs(
        build_in_memory_scheduling_repos(store).reader,
        get_access_guard(),
        JobRegistry(list(definitions)),
        InMemoryScheduleSource(schedules),
        CronScheduleEvaluator(),
    )


def _keys(page: object) -> list[str]:
    return [status.definition.job_key for status in page.items]  # type: ignore[attr-defined]


async def test_jobs_come_by_title_ignoring_case_unless_sorted() -> None:
    """The default order is the title, so it does not depend on registration."""
    case = await _listing(
        JobDefinition(job_key="z", title="beta"),
        JobDefinition(job_key="y", title="Alpha"),
        JobDefinition(job_key="x", title="Charlie"),
        schedules={},
    )

    assert _keys(await case.handle(_query(), ADMIN)) == ["y", "z", "x"]
    desc = _query(sort=JobSort.TITLE, order=SortOrder.DESC)
    assert _keys(await case.handle(desc, ADMIN)) == ["x", "z", "y"]


async def test_a_job_with_no_next_run_sorts_last_in_either_direction() -> None:
    """An unscheduled job has nothing to compare, so it follows the rest."""
    case = await _listing(
        JobDefinition(job_key="late", schedule_key="late", title="B"),
        JobDefinition(job_key="soon", schedule_key="soon", title="C"),
        JobDefinition(job_key="never", title="A"),
        schedules={"late": "0 5 * * *", "soon": "0 4 * * *"},
    )

    asc = _query(sort=JobSort.NEXT_RUN_AT)
    desc = _query(sort=JobSort.NEXT_RUN_AT, order=SortOrder.DESC)
    assert _keys(await case.handle(asc, ADMIN)) == ["soon", "late", "never"]
    assert _keys(await case.handle(desc, ADMIN)) == ["late", "soon", "never"]


async def test_jobs_sort_by_when_they_last_ran_never_run_last() -> None:
    """The last run's start orders them, and a job that never ran has none."""
    store = InMemorySchedulingStore()
    registry = JobRegistry(
        [
            JobDefinition(job_key="first", title="First"),
            JobDefinition(job_key="second", title="Second"),
            JobDefinition(job_key="idle", title="Idle"),
        ]
    )
    for key, moment in (("second", NOW), ("first", NOW - timedelta(days=1))):
        await RunJobNow(
            create_in_memory_scheduling_uow(store), get_access_guard(), registry
        ).handle(RunJobNowCommand(job_key=key, now=moment), ADMIN)
    case = ListJobs(
        build_in_memory_scheduling_repos(store).reader,
        get_access_guard(),
        registry,
        InMemoryScheduleSource({}),
        CronScheduleEvaluator(),
    )

    asc = _query(sort=JobSort.LAST_RUN)
    desc = _query(sort=JobSort.LAST_RUN, order=SortOrder.DESC)
    assert _keys(await case.handle(asc, ADMIN)) == ["first", "second", "idle"]
    assert _keys(await case.handle(desc, ADMIN)) == ["second", "first", "idle"]


async def test_q_keeps_the_jobs_whose_title_or_description_contains_it() -> None:
    """Text matches the title and the description, ignoring case and accents."""
    case = await _listing(
        JobDefinition(job_key="a", title="Tidy up", description="Removes old files"),
        JobDefinition(job_key="b", title="Café check", description="Looks at cafés"),
        JobDefinition(job_key="c", title="Backup", description="Saves a copy"),
        schedules={},
    )

    assert _keys(await case.handle(_query(q="CAFE"), ADMIN)) == ["b"]
    assert _keys(await case.handle(_query(q="old files"), ADMIN)) == ["a"]
    page = await case.handle(_query(q="zzz"), ADMIN)
    assert (_keys(page), page.total) == ([], 0)


async def test_jobs_are_paged_by_a_cursor_and_report_how_many_there_are() -> None:
    """A small page names the next one, and the total counts every match."""
    case = await _listing(
        *[JobDefinition(job_key=f"j{n}", title=f"Job {n}") for n in range(5)],
        schedules={},
    )

    first = await case.handle(_query(limit=2), ADMIN)
    assert (_keys(first), first.total) == (["j0", "j1"], 5)
    assert first.next is not None
    second = await case.handle(_query(limit=2, after=first.next), ADMIN)
    assert _keys(second) == ["j2", "j3"]


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
    one = await query.handle(GetJobHistoryQuery(job_key="x", limit=1), ADMIN)
    assert len(one.items) == 1
    with pytest.raises(UnknownJobError):
        await query.handle(GetJobHistoryQuery(job_key="missing"), ADMIN)
    with pytest.raises(ValidationError):
        GetJobHistoryQuery(job_key="x", limit=0)


@pytest.mark.parametrize("order", list(SortOrder))
@pytest.mark.parametrize("sort", list(JobRunSort))
async def test_history_sorts_by_every_key(sort: JobRunSort, order: SortOrder) -> None:
    """Every key the history offers orders a run, in both directions."""
    store = InMemorySchedulingStore()
    registry = JobRegistry([JobDefinition(job_key="x")])
    await RunJobNow(
        create_in_memory_scheduling_uow(store), get_access_guard(), registry
    ).handle(RunJobNowCommand(job_key="x", now=NOW), ADMIN)
    query = GetJobHistory(
        build_in_memory_scheduling_repos(store).reader, get_access_guard(), registry
    )

    page = await query.handle(
        GetJobHistoryQuery(job_key="x", sort=sort, order=order), ADMIN
    )

    assert len(page.items) == 1
    assert page.total == 1
    assert page.next is None
