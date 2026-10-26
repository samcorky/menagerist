"""Cron timing and missed-run policy at fixed instants."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.modules.scheduling.adapters.platform.cron import CronSchedule
from app.modules.scheduling.domain.schedule import MissedRun, due_fire
from app.shared_kernel.errors import ValidationError


def instant(value: str) -> datetime:
    """Parse a literal UTC test instant."""
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


@pytest.mark.parametrize(
    ("expression", "start", "end", "expected"),
    [
        (
            "0 3 * * *",
            "2026-03-28T03:00",
            "2026-03-30T03:00",
            ["2026-03-29T02:00", "2026-03-30T02:00"],
        ),
        ("30 1 * * *", "2026-03-29T00:00", "2026-03-29T02:00", ["2026-03-29T01:00"]),
        ("30 1 * * *", "2026-10-25T00:00", "2026-10-25T03:00", ["2026-10-25T00:30"]),
        (
            "0 * * * *",
            "2026-10-24T23:30",
            "2026-10-25T02:00",
            ["2026-10-25T00:00", "2026-10-25T01:00", "2026-10-25T02:00"],
        ),
        (
            "0 3 * * *",
            "2026-10-24T02:00",
            "2026-10-26T03:00",
            ["2026-10-25T03:00", "2026-10-26T03:00"],
        ),
    ],
)
def test_dst_fire_times(
    expression: str, start: str, end: str, expected: list[str]
) -> None:
    """Daily schedules follow wall time; hourly jobs include both autumn hours."""
    schedule = CronSchedule(expression=expression, zone=ZoneInfo("Europe/London"))
    assert list(schedule.fires_between(instant(start), instant(end))) == [
        instant(value) for value in expected
    ]


def test_long_window_does_not_truncate_the_latest_fire() -> None:
    """An outage spanning more than 1,000 fires still reaches the latest one."""
    schedule = CronSchedule(expression="* * * * *", zone=ZoneInfo("UTC"))
    fires = list(
        schedule.fires_between(instant("2026-01-01T00:00"), instant("2026-01-02T00:00"))
    )
    assert len(fires) == 1440
    assert fires[-1] == instant("2026-01-02T00:00")


@pytest.mark.parametrize("expression", ["", "bad", "60 * * * *", "* * * * * *"])
def test_invalid_cron_is_rejected(expression: str) -> None:
    """Only valid five-field, minute-resolution expressions are accepted."""
    with pytest.raises(ValidationError):
        CronSchedule(expression=expression, zone=ZoneInfo("UTC"))


def test_cron_rejects_naive_datetimes() -> None:
    """Both interval endpoints must identify an absolute instant."""
    schedule = CronSchedule(expression="* * * * *", zone=ZoneInfo("UTC"))
    with pytest.raises(ValidationError):
        list(schedule.fires_between(datetime(2026, 1, 1), instant("2026-01-02T00:00")))
    with pytest.raises(ValidationError):
        list(schedule.fires_between(instant("2026-01-01T00:00"), datetime(2026, 1, 2)))


@pytest.mark.parametrize(
    ("watermark", "latest", "policy", "expected"),
    [
        (None, "2026-01-01T03:00", MissedRun.RUN_ONCE, None),
        ("2026-01-01T02:00", None, MissedRun.RUN_ONCE, None),
        (
            "2026-01-01T02:00",
            "2026-01-01T03:00",
            MissedRun.RUN_ONCE,
            "2026-01-01T03:00",
        ),
        ("2026-01-01T03:00", "2026-01-01T03:00", MissedRun.RUN_ONCE, None),
        ("2026-01-01T02:00", "2026-01-01T04:01", MissedRun.RUN_ONCE, None),
        ("2026-01-01T02:00", "2026-01-01T03:00", MissedRun.SKIP, None),
        ("2026-01-01T02:00", "2026-01-01T03:59", MissedRun.SKIP, "2026-01-01T03:59"),
    ],
)
def test_due_policy(
    watermark: str | None, latest: str | None, policy: MissedRun, expected: str | None
) -> None:
    """New jobs do not backfill; existing jobs obey watermark and lateness."""
    result = due_fire(
        instant(latest) if latest else None,
        watermark=instant(watermark) if watermark else None,
        now=instant("2026-01-01T04:00"),
        missed=policy,
        max_lateness=timedelta(hours=1),
    )
    assert result == (instant(expected) if expected else None)


@pytest.mark.parametrize("which", ["latest", "watermark", "now"])
def test_due_policy_rejects_naive_instants(which: str) -> None:
    """A timezone-less watermark, clock or occurrence cannot schedule a run."""
    values = {
        name: instant("2026-01-01T03:00") for name in ["latest", "watermark", "now"]
    }
    values[which] = values[which].replace(tzinfo=None)
    with pytest.raises(ValidationError):
        due_fire(
            values["latest"],
            watermark=values["watermark"],
            now=values["now"],
            missed=MissedRun.RUN_ONCE,
            max_lateness=timedelta(hours=1),
        )


def test_due_policy_compares_autumn_folds_as_absolute_instants() -> None:
    """The second autumn hour remains later than the first with the same zone."""
    zone = ZoneInfo("Europe/London")
    latest = datetime(2026, 10, 25, 1, 0, tzinfo=zone, fold=1)
    watermark = datetime(2026, 10, 25, 1, 30, tzinfo=zone, fold=0)
    now = datetime(2026, 10, 25, 1, 1, tzinfo=zone, fold=1)
    assert due_fire(
        latest,
        watermark=watermark,
        now=now,
        missed=MissedRun.SKIP,
        max_lateness=timedelta(hours=1),
    ) == instant("2026-10-25T01:00")


def test_run_once_drops_an_occurrence_beyond_its_lateness_budget() -> None:
    """Catch-up never executes an occurrence older than max_lateness."""
    assert (
        due_fire(
            instant("2026-01-01T03:00"),
            watermark=instant("2026-01-01T00:00"),
            now=instant("2026-01-01T04:01"),
            missed=MissedRun.RUN_ONCE,
            max_lateness=timedelta(hours=1),
        )
        is None
    )


def test_daily_cron_resuming_inside_repeated_hour_never_replays_a_fire() -> None:
    """A fold-zero occurrence before the lower UTC bound is already in the past."""
    schedule = CronSchedule(expression="30 1 * * *", zone=ZoneInfo("Europe/London"))
    assert (
        list(
            schedule.fires_between(
                instant("2026-10-25T01:00"), instant("2026-10-25T01:40")
            )
        )
        == []
    )
