"""Instance timezone, history limits and source tracking."""

import pytest
from pydantic import ValidationError

from app.platform.config import SchedulerSettings, get_scheduler_settings


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
    monkeypatch.setenv("MENAGERIST_RUN_HISTORY_PER_JOB", "12")
    get_scheduler_settings.cache_clear()
    try:
        settings = get_scheduler_settings()
        assert settings.run_history_per_job == 12
        assert settings.source_of("run_history_per_job") == "env"
        assert get_scheduler_settings() is settings
    finally:
        get_scheduler_settings.cache_clear()
    monkeypatch.setenv("MENAGERIST_RUN_HISTORY_PER_JOB", "0")
    with pytest.raises(ValidationError):
        SchedulerSettings()


def test_default_history_and_frozen_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Defaults are logged as defaults, and settings remain frozen."""
    monkeypatch.delenv("MENAGERIST_RUN_HISTORY_PER_JOB", raising=False)
    settings = SchedulerSettings()
    assert settings.run_history_per_job == 100
    assert settings.source_of("run_history_per_job") == "default"
    with pytest.raises(ValidationError):
        settings.run_history_per_job = 1  # type: ignore[misc]
