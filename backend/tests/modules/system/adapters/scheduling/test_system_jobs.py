import pytest

from app.modules.system.adapters.scheduling import jobs
from app.platform.config.release import ReleaseSettings


def settings(*, enabled: bool, schedule: str = "20 5 * * *") -> ReleaseSettings:
    """Release settings as a deployment would supply them."""
    return ReleaseSettings(check_enabled=enabled, check_schedule=schedule)


@pytest.fixture
def release_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Read the deployment switch from this test rather than the environment."""
    monkeypatch.setattr(jobs, "get_release_settings", lambda: settings(enabled=True))


def test_the_update_check_is_registered_with_its_deployment_schedule(
    release_settings: None,
) -> None:
    """The update check is registered with its deployment schedule."""
    contribution = jobs.system_job_contribution()

    keys = [binding.definition.job_key for binding in contribution.bindings()]
    assert keys == ["system.update_check"]
    assert contribution.schedules() == {"release.check_schedule": "20 5 * * *"}


def test_a_turned_off_deployment_registers_no_job_at_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With checks off there is no cron to evaluate and no row to run by hand."""
    monkeypatch.setattr(jobs, "get_release_settings", lambda: settings(enabled=False))

    contribution = jobs.system_job_contribution()

    assert contribution.bindings() == []
    assert contribution.schedules() == {}


def test_an_empty_schedule_still_registers_the_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty schedule only stops the timer; Check now still works."""
    monkeypatch.setattr(
        jobs, "get_release_settings", lambda: settings(enabled=True, schedule="")
    )

    contribution = jobs.system_job_contribution()

    assert [b.definition.job_key for b in contribution.bindings()] == [
        "system.update_check"
    ]
    assert contribution.schedules() == {"release.check_schedule": ""}
