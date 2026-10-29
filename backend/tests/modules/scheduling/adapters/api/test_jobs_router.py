from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid7

import pytest
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.scheduling.adapters.api.dependencies import (
    get_job_history_use_case,
    get_list_jobs_use_case,
    get_run_job_now_use_case,
)
from app.modules.scheduling.adapters.persistence.in_memory_job_run_reader import (
    InMemoryJobRunReader,
)
from app.modules.scheduling.adapters.persistence.in_memory_store import (
    InMemorySchedulingStore,
)
from app.modules.scheduling.adapters.persistence.unit_of_work import (
    create_in_memory_scheduling_uow,
)
from app.modules.scheduling.adapters.platform.cron_evaluator import (
    CronScheduleEvaluator,
)
from app.modules.scheduling.adapters.platform.in_memory_schedule_source import (
    InMemoryScheduleSource,
)
from app.modules.scheduling.application.get_job_history import GetJobHistory
from app.modules.scheduling.application.list_jobs import ListJobs
from app.modules.scheduling.application.run_job_now import RunJobNow
from app.modules.scheduling.domain.job_run import JobRun, RunStatus
from app.modules.scheduling.domain.registry import JobRegistry
from app.shared_kernel.jobs import JobDefinition

BASE = "/api/v1/scheduling/jobs"

type AsUser = Callable[..., None]


def build(
    as_user: AsUser, role: str = "admin"
) -> tuple[TestClient, InMemorySchedulingStore]:
    """The app signed in with the given role, over an in-memory scheduler."""
    registry = JobRegistry(
        [
            JobDefinition(
                job_key="backup.create",
                schedule_key="backup.schedule",
                title="Back up everything",
                description="Saves a full copy.",
            ),
            JobDefinition(
                job_key="manual.only", run_now_allowed=False, confirm_required=True
            ),
        ]
    )
    store = InMemorySchedulingStore()
    reader = InMemoryJobRunReader(store)
    guard = get_access_guard()
    schedules = InMemoryScheduleSource({"backup.schedule": "0 3 * * *"})
    app = create_app()
    as_user(app, uuid7(), role)
    app.dependency_overrides[get_list_jobs_use_case] = lambda: ListJobs(
        reader, guard, registry, schedules, CronScheduleEvaluator()
    )
    app.dependency_overrides[get_job_history_use_case] = lambda: GetJobHistory(
        reader, guard, registry
    )
    app.dependency_overrides[get_run_job_now_use_case] = lambda: RunJobNow(
        create_in_memory_scheduling_uow(store), guard, registry
    )
    return TestClient(app), store


def test_it_lists_every_job_with_its_schedule(as_user: AsUser) -> None:
    """Scheduled jobs carry a next run; unscheduled ones carry none."""
    client, _ = build(as_user)
    response = client.get(BASE)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    jobs = {job["job_key"]: job for job in response.json()}
    assert set(jobs) == {"backup.create", "manual.only"}
    assert jobs["backup.create"]["title"] == "Back up everything"
    assert jobs["backup.create"]["description"] == "Saves a full copy."
    assert jobs["manual.only"]["title"] == "Only"
    assert jobs["backup.create"]["schedule"] == "0 3 * * *"
    assert jobs["backup.create"]["next_run_at"] is not None
    assert jobs["manual.only"]["schedule"] is None
    assert jobs["manual.only"]["next_run_at"] is None
    assert jobs["manual.only"]["run_now_allowed"] is False


def test_it_shows_work_in_progress(as_user: AsUser) -> None:
    """The listing reports the run currently waiting or running."""
    client, store = build(as_user)
    run = JobRun.create(job_key="backup.create", scheduled_for=datetime.now(UTC))
    store.runs[run.id] = run
    active = next(
        job for job in client.get(BASE).json() if job["job_key"] == "backup.create"
    )["active_run"]
    assert (active["id"], active["status"]) == (str(run.id), "queued")


def test_it_names_the_setting_behind_each_schedule(as_user: AsUser) -> None:
    """A job points at the setting that holds its schedule, when it has one."""
    client, _ = build(as_user)
    jobs = {job["job_key"]: job for job in client.get(BASE).json()}
    assert jobs["backup.create"]["schedule_key"] == "backup.schedule"
    assert jobs["manual.only"]["schedule_key"] is None


def test_it_says_which_jobs_want_a_confirmation(as_user: AsUser) -> None:
    """The interface is told which jobs to ask about before running by hand."""
    client, _ = build(as_user)
    jobs = {job["job_key"]: job for job in client.get(BASE).json()}
    assert jobs["manual.only"]["confirm_required"] is True
    assert jobs["backup.create"]["confirm_required"] is False


def test_it_reports_the_latest_run_of_each_job(as_user: AsUser) -> None:
    """The newest run is returned whatever its outcome; a job never run has none."""
    client, store = build(as_user)
    for minute, status in enumerate([RunStatus.SUCCEEDED, RunStatus.FAILED]):
        run = JobRun.create(
            job_key="backup.create",
            scheduled_for=datetime(2026, 10, 28, 3, minute, tzinfo=UTC),
        )
        run.status = status
        store.runs[run.id] = run
    jobs = {job["job_key"]: job for job in client.get(BASE).json()}
    assert jobs["backup.create"]["last_run"]["status"] == "failed"
    assert jobs["manual.only"]["last_run"] is None


def test_history_is_limited_and_newest_first(as_user: AsUser) -> None:
    """Recent runs come back newest first, up to the requested limit."""
    client, store = build(as_user)
    for minute in range(3):
        run = JobRun.create(
            job_key="backup.create",
            scheduled_for=datetime(2026, 10, 28, 3, minute, tzinfo=UTC),
        )
        run.status = RunStatus.SUCCEEDED
        store.runs[run.id] = run
    response = client.get(f"{BASE}/backup.create/runs", params={"limit": 2})
    assert response.status_code == 200
    scheduled = [run["scheduled_for"] for run in response.json()]
    assert len(scheduled) == 2
    assert scheduled == sorted(scheduled, reverse=True)


def test_history_of_an_unknown_job_is_not_found(as_user: AsUser) -> None:
    """A mistyped key is a 404 rather than an empty list."""
    client, _ = build(as_user)
    assert client.get(f"{BASE}/nope/runs").status_code == 404


@pytest.mark.parametrize("limit", [0, 101])
def test_out_of_range_limits_are_rejected(as_user: AsUser, limit: int) -> None:
    """The limit is bounded before it reaches the query."""
    client, _ = build(as_user)
    response = client.get(f"{BASE}/backup.create/runs", params={"limit": limit})
    assert response.status_code == 422


def test_run_now_queues_a_run_for_the_requester(as_user: AsUser) -> None:
    """Running by hand answers 202 with a queued run attributed to the admin."""
    client, store = build(as_user)
    response = client.post(f"{BASE}/backup.create/run")
    assert response.status_code == 202
    body = response.json()
    assert (body["job_key"], body["status"]) == ("backup.create", "queued")
    assert body["requested_by"] is not None
    assert [run.status for run in store.runs.values()] == [RunStatus.QUEUED]


def test_run_now_reuses_active_work(as_user: AsUser) -> None:
    """Pressing the button twice does not stack runs."""
    client, store = build(as_user)
    first = client.post(f"{BASE}/backup.create/run").json()
    second = client.post(f"{BASE}/backup.create/run").json()
    assert first["id"] == second["id"]
    assert len(store.runs) == 1


def test_run_now_refuses_jobs_that_forbid_it(as_user: AsUser) -> None:
    """A job that cannot be run by hand answers 409."""
    client, _ = build(as_user)
    assert client.post(f"{BASE}/manual.only/run").status_code == 409


def test_run_now_of_an_unknown_job_is_not_found(as_user: AsUser) -> None:
    """A mistyped key is a 404."""
    client, _ = build(as_user)
    assert client.post(f"{BASE}/nope/run").status_code == 404


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", BASE),
        ("get", f"{BASE}/backup.create/runs"),
        ("post", f"{BASE}/backup.create/run"),
    ],
)
def test_members_are_refused(as_user: AsUser, method: str, path: str) -> None:
    """Everything here is administrative."""
    client, _ = build(as_user, role="member")
    assert client.request(method, path).status_code == 403
