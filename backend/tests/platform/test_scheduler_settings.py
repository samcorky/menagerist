"""Instance timezone, history limits and source tracking."""

import pytest
from pydantic import ValidationError

from app.platform.config import SchedulerSettings, get_scheduler_settings


def test_worker_heartbeat_timeout_default_and_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Liveness expiry is positive, source-tracked and configurable in seconds."""
    name = "MENAGERIST_SCHEDULER_WORKER_HEARTBEAT_TIMEOUT_SECONDS"
    monkeypatch.delenv(name, raising=False)
    defaults = SchedulerSettings()
    assert defaults.worker_heartbeat_timeout_seconds == 300
    assert defaults.worker_heartbeat_interval_seconds == 60
    assert defaults.source_of("worker_heartbeat_timeout_seconds") == "default"
    monkeypatch.setenv(name, "120")
    monkeypatch.setenv("MENAGERIST_SCHEDULER_WORKER_HEARTBEAT_INTERVAL_SECONDS", "30")
    configured = SchedulerSettings()
    assert configured.worker_heartbeat_timeout_seconds == 120
    assert configured.worker_heartbeat_interval_seconds == 30
    assert configured.source_of("worker_heartbeat_interval_seconds") == "env"
    assert configured.source_of("worker_heartbeat_timeout_seconds") == "env"


@pytest.mark.parametrize("value", ["0", "-1", "invalid"])
def test_worker_heartbeat_timeout_rejects_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    """Invalid expiry values fail during startup settings validation."""
    monkeypatch.setenv("MENAGERIST_SCHEDULER_WORKER_HEARTBEAT_TIMEOUT_SECONDS", value)
    with pytest.raises(ValidationError):
        SchedulerSettings()


@pytest.mark.parametrize(
    ("interval", "timeout"), [(0, 120), (-1, 120), (120, 120), (121, 120)]
)
def test_heartbeat_interval_must_be_positive_and_shorter_than_timeout(
    interval: int,
    timeout: int,
) -> None:
    """A worker must be due to check in before diagnostics consider it stale."""
    with pytest.raises(ValidationError):
        SchedulerSettings(
            worker_heartbeat_interval_seconds=interval,
            worker_heartbeat_timeout_seconds=timeout,
        )


@pytest.mark.parametrize(
    ("tz", "fallback", "expected"),
    [
        (None, None, "UTC"),
        ("Europe/London", "America/New_York", "America/New_York"),
        (None, "America/New_York", "America/New_York"),
        ("Europe/London", None, "Europe/London"),
        ("Europe/London", "", "Europe/London"),
        ("", "Europe/London", "Europe/London"),
        ("", "", "UTC"),
    ],
)
def test_timezone_precedence(
    monkeypatch: pytest.MonkeyPatch, tz: str | None, fallback: str | None, expected: str
) -> None:
    """The application timezone overrides Docker TZ; empty aliases fall through."""
    for name, value in [("TZ", tz), ("MENAGERIST_TIMEZONE", fallback)]:
        monkeypatch.delenv(name, raising=False)
        if value is not None:
            monkeypatch.setenv(name, value)
    settings = SchedulerSettings()
    assert str(settings.timezone) == expected
    assert settings.model_dump(mode="json")["timezone"] == expected
    assert settings.source_of("timezone") == (
        "default" if not tz and not fallback else "env"
    )


@pytest.mark.parametrize("zone", ["Not/AZone", "GMT+25"])
def test_invalid_timezone_is_a_validation_error(
    monkeypatch: pytest.MonkeyPatch, zone: str
) -> None:
    """Unknown zones fail at settings construction instead of worker execution."""
    monkeypatch.setenv("TZ", zone)
    with pytest.raises(ValidationError):
        SchedulerSettings()


def test_history_limit_and_cached_getter(monkeypatch: pytest.MonkeyPatch) -> None:
    """History is configurable, positive and cached consistently with other groups."""
    monkeypatch.setenv("MENAGERIST_SCHEDULER_RUN_HISTORY_PER_JOB", "12")
    get_scheduler_settings.cache_clear()
    try:
        settings = get_scheduler_settings()
        assert settings.run_history_per_job == 12
        assert settings.source_of("run_history_per_job") == "env"
        assert get_scheduler_settings() is settings
    finally:
        get_scheduler_settings.cache_clear()
    monkeypatch.setenv("MENAGERIST_SCHEDULER_RUN_HISTORY_PER_JOB", "0")
    with pytest.raises(ValidationError):
        SchedulerSettings()


def test_default_history_and_frozen_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Defaults are logged as defaults, and settings remain frozen."""
    monkeypatch.delenv("MENAGERIST_SCHEDULER_RUN_HISTORY_PER_JOB", raising=False)
    settings = SchedulerSettings()
    assert settings.run_history_per_job == 100
    assert settings.source_of("run_history_per_job") == "default"
    with pytest.raises(ValidationError):
        settings.run_history_per_job = 1  # type: ignore[misc]
