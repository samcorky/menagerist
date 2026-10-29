"""The identity module's contribution to the scheduler."""

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock

from app.modules.identity.adapters.scheduling import jobs as identity_jobs
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    import pytest


def test_it_contributes_one_titled_job_on_a_deployment_schedule() -> None:
    """Expired sign-ins are purged by a job an administrator can read about."""
    [binding] = identity_jobs.identity_job_contribution().bindings()
    job = binding.definition
    assert job.job_key == "identity.purge_expired"
    assert job.schedule_key == "identity.purge_expired_schedule"
    assert job.title.strip()
    assert job.description.strip()
    assert binding.handler is identity_jobs.purge_expired_credentials


async def test_the_job_runs_the_purge_as_the_given_actor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The handler builds the use case and runs it for the worker's actor."""
    handle = AsyncMock()
    monkeypatch.setattr(identity_jobs, "create_identity_uow", Mock())
    monkeypatch.setattr(identity_jobs, "get_session_factory", Mock())
    monkeypatch.setattr(
        identity_jobs, "PurgeExpiredCredentials", Mock(return_value=Mock(handle=handle))
    )
    await identity_jobs.purge_expired_credentials(SYSTEM_ACTOR)
    assert handle.await_args is not None
    [command, actor] = handle.await_args.args
    assert actor is SYSTEM_ACTOR
    assert command.now.tzinfo is not None


def test_the_schedule_comes_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """The deployment value feeds the schedule source; empty keeps the job off."""
    monkeypatch.setattr(
        identity_jobs,
        "get_identity_settings",
        Mock(return_value=Mock(purge_expired_schedule="5 4 * * *")),
    )
    contribution = identity_jobs.identity_job_contribution()
    assert contribution.schedules() == {"identity.purge_expired_schedule": "5 4 * * *"}
