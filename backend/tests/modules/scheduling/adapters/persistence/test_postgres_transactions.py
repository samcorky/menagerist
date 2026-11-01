"""Concurrency guarantees require independent connections and real commits."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.modules.scheduling.adapters.persistence.models import (
    JobRunModel,
    ScheduleCursorModel,
    WorkerHeartbeatModel,
)
from app.modules.scheduling.adapters.persistence.unit_of_work import (
    build_scheduling_repos,
    create_scheduling_uow,
)
from app.modules.scheduling.adapters.platform.cron_evaluator import (
    CronScheduleEvaluator,
)
from app.modules.scheduling.adapters.platform.in_memory_schedule_source import (
    InMemoryScheduleSource,
)
from app.modules.scheduling.application.tick_schedules import (
    TickSchedules,
    TickSchedulesCommand,
)
from app.modules.scheduling.domain.errors import LostClaimError
from app.modules.scheduling.domain.job_run import JobRun, RunStatus
from app.modules.scheduling.domain.registry import JobRegistry
from app.platform.unit_of_work import SessionBoundUnitOfWork
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.jobs import JobDefinition, Lane, Overlap

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

pytestmark = pytest.mark.integration
NOW = datetime(2026, 10, 26, 12, tzinfo=UTC)


@pytest.fixture
async def sessions(
    postgres_url: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Use independent transactions, clearing only these test database tables."""
    engine = create_async_engine(postgres_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        async with factory.begin() as session:
            for model in (JobRunModel, ScheduleCursorModel, WorkerHeartbeatModel):
                await session.execute(delete(model))
        await engine.dispose()


async def enqueue(
    sessions: async_sessionmaker[AsyncSession], run: JobRun, *, manual: bool = False
) -> JobRun:
    """Commit one submission on its own connection."""
    async with sessions.begin() as session:
        return await build_scheduling_repos(session).queue.enqueue(
            run, deduplicate_active=manual
        )


async def claim(
    sessions: async_sessionmaker[AsyncSession], worker: str
) -> JobRun | None:
    """Commit one claim on its own connection."""
    async with sessions.begin() as session:
        return await build_scheduling_repos(session).queue.claim(
            list(Lane), worker, NOW
        )


@pytest.mark.parametrize("policy", list(Overlap))
async def test_concurrent_fire_submissions_are_unique(
    sessions: async_sessionmaker[AsyncSession], policy: Overlap
) -> None:
    """Independent ticks cannot insert the same scheduled occurrence twice."""
    job = JobDefinition(job_key="x", overlap=policy)
    runs = await asyncio.wait_for(
        asyncio.gather(
            *(enqueue(sessions, JobRun.for_schedule(job, NOW)) for _ in range(8))
        ),
        timeout=10,
    )
    assert len({run.id for run in runs}) == 1
    async with sessions() as session:
        assert (
            len(await build_scheduling_repos(session).reader.history("x", limit=100))
            == 1
        )


@pytest.mark.parametrize(
    ("policy", "manual", "count"),
    [
        (Overlap.SKIP, False, 1),
        (Overlap.COALESCE, False, 2),
        (Overlap.QUEUE, False, 9),
        (Overlap.QUEUE, True, 1),
    ],
)
async def test_concurrent_overlap_decisions(
    sessions: async_sessionmaker[AsyncSession],
    policy: Overlap,
    manual: bool,
    count: int,
) -> None:
    """A running job can gain only the waiters permitted by its overlap policy."""
    first = await enqueue(
        sessions, JobRun.create(job_key="x", scheduled_for=NOW, overlap=policy)
    )
    assert await claim(sessions, "first") is not None
    await asyncio.wait_for(
        asyncio.gather(
            *(
                enqueue(
                    sessions,
                    JobRun.create(job_key="x", scheduled_for=NOW, overlap=policy),
                    manual=manual,
                )
                for _ in range(8)
            )
        ),
        timeout=10,
    )
    async with sessions() as session:
        repos = build_scheduling_repos(session)
        assert len(await repos.reader.history("x", limit=100)) == count
        active = await repos.reader.active_run("x")
        assert active is not None
        assert active.id == first.id


async def test_two_workers_claim_distinct_jobs_and_keep_each_job_serial(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Queue policy permits a backlog, while two workers still execute it serially."""
    for key, lane in [("x", Lane.HEAVY), ("x", Lane.HEAVY), ("y", Lane.DEFAULT)]:
        await enqueue(
            sessions,
            JobRun.create(
                job_key=key, scheduled_for=NOW, overlap=Overlap.QUEUE, lane=lane
            ),
        )
    runs = await asyncio.wait_for(
        asyncio.gather(*(claim(sessions, str(index)) for index in range(8))), timeout=10
    )
    claimed = [run for run in runs if run is not None]
    assert len(claimed) == len({run.id for run in claimed}) == 2
    assert {run.job_key for run in claimed} == {"x", "y"}
    async with sessions.begin() as session:
        for run in claimed:
            assert run.worker_id is not None
            await build_scheduling_repos(session).recorder.finish(
                run.id, run.worker_id, RunStatus.SUCCEEDED, NOW
            )
    remaining = await claim(sessions, "next")
    assert remaining is not None
    assert remaining.job_key == "x"


async def test_uncommitted_claim_does_not_block_another_job(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """SKIP LOCKED plus a non-blocking job lock bypass a claimant's whole job."""
    for key in ("x", "x", "y"):
        await enqueue(
            sessions,
            JobRun.create(job_key=key, scheduled_for=NOW, overlap=Overlap.QUEUE),
        )
    async with sessions.begin() as first_session:
        first = await build_scheduling_repos(first_session).queue.claim(
            list(Lane), "first", NOW
        )
        assert first is not None
        assert first.job_key == "x"
        second = await asyncio.wait_for(claim(sessions, "second"), timeout=3)
        assert second is not None
        assert second.job_key == "y"
    assert await claim(sessions, "third") is None


async def test_busy_tick_does_not_block_another_lane(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A tick's job lock must not stall the default lane behind a heavy job."""
    heavy = await enqueue(
        sessions, JobRun.create(job_key="heavy", scheduled_for=NOW, lane=Lane.HEAVY)
    )
    normal = await enqueue(sessions, JobRun.create(job_key="normal", scheduled_for=NOW))
    async with sessions.begin() as ticking:
        await build_scheduling_repos(ticking).cursors.observe(
            "heavy", expression="* * * * *", timezone="UTC", now=NOW
        )
        selected = await asyncio.wait_for(claim(sessions, "worker"), timeout=3)
        assert selected is not None
        assert selected.id == normal.id
    selected = await claim(sessions, "worker")
    assert selected is not None
    assert selected.id == heavy.id


async def test_caller_transaction_rolls_back_data_cursor_and_enqueue_together(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Enqueue, other writes and cursor changes share the caller's transaction."""
    run = JobRun.create(job_key="x", scheduled_for=NOW)
    async with sessions() as session:
        uow = SessionBoundUnitOfWork(session, build_scheduling_repos)
        with pytest.raises(RuntimeError, match="abort"):  # noqa: PT012
            async with uow as repos:
                await repos.recorder.worker_heartbeat("writer", NOW)
                await repos.cursors.observe(
                    "x", expression="* * * * *", timezone="UTC", now=NOW
                )
                await repos.queue.enqueue(run)
                await repos.cursors.advance("x", NOW + timedelta(minutes=1))
                raise RuntimeError("abort")
    async with sessions() as session:
        assert not (await session.scalars(select(JobRunModel))).all()
        assert not (await session.scalars(select(ScheduleCursorModel))).all()
        assert not await build_scheduling_repos(session).reader.worker_alive(NOW)
    durable_uow = create_scheduling_uow(sessions)
    async with durable_uow as repos:
        await repos.queue.enqueue(run)
        await repos.cursors.observe(
            "x", expression="* * * * *", timezone="UTC", now=NOW
        )
        await repos.recorder.worker_heartbeat("writer", NOW)
        await durable_uow.commit()
    async with sessions() as session:
        repos = build_scheduling_repos(session)
        assert (await repos.reader.get(run.id)).status is RunStatus.QUEUED
        assert await repos.reader.worker_alive(NOW)
        cursor = await session.get(ScheduleCursorModel, "x")
        assert cursor is not None
        assert cursor.checked_until == NOW


async def test_concurrent_ticks_advance_one_cursor_and_submit_one_fire(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Each tick holds its observation window until submission and cursor commit."""

    def tick() -> TickSchedules:
        return TickSchedules(
            create_scheduling_uow(sessions),
            InMemoryAccessGuard(),
            JobRegistry([JobDefinition(job_key="x", schedule_key="x")]),
            InMemoryScheduleSource({"x": "* * * * *"}),
            CronScheduleEvaluator(),
        )

    await tick().handle(TickSchedulesCommand(now=NOW, timezone="UTC"), SYSTEM_ACTOR)
    later = NOW + timedelta(minutes=1)
    await asyncio.wait_for(
        asyncio.gather(
            *(
                tick().handle(
                    TickSchedulesCommand(now=later, timezone="UTC"), SYSTEM_ACTOR
                )
                for _ in range(4)
            )
        ),
        timeout=10,
    )
    async with sessions() as session:
        assert (
            len(await build_scheduling_repos(session).reader.history("x", limit=100))
            == 1
        )
        cursor = await session.get(ScheduleCursorModel, "x")
        assert cursor is not None
        assert cursor.checked_until == later


async def test_reaper_fences_a_claimant_with_a_cached_running_snapshot(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A late completion must reload the current row and preserve abandonment."""
    queued = await enqueue(sessions, JobRun.create(job_key="x", scheduled_for=NOW))
    assert await claim(sessions, "worker") is not None
    async with sessions() as stale:
        cached = await stale.get(JobRunModel, queued.id)
        assert cached is not None
        assert cached.status == RunStatus.RUNNING
        async with sessions.begin() as reaper:
            assert (
                await build_scheduling_repos(reaper).recorder.reap_abandoned(
                    NOW + timedelta(minutes=1), NOW + timedelta(minutes=2)
                )
                == 1
            )
        with pytest.raises(LostClaimError):
            await build_scheduling_repos(stale).recorder.finish(
                queued.id, "worker", RunStatus.SUCCEEDED, NOW
            )
    async with sessions() as session:
        assert (
            await build_scheduling_repos(session).reader.get(queued.id)
        ).status is RunStatus.ABANDONED
