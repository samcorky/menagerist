from typing import Annotated
from zoneinfo import ZoneInfo

import pytest
from pydantic import Field

from app.modules.settings.adapters.platform.deployment_catalogue import (
    build_catalogue,
    deployment_catalogue,
)
from app.modules.settings.domain.errors import InvalidSettingValueError
from app.modules.settings.domain.setting import SettingScope
from app.platform.config import (
    BackupSettings,
    MenageristBaseSettings,
    SchedulerSettings,
)
from app.platform.config._discovery import discover
from app.platform.config._markers import Public, Scope, Tunable


class Display(MenageristBaseSettings, group="display"):
    """A per-user setting that reads as a ZoneInfo."""

    timezone: Annotated[ZoneInfo, Tunable(scope=Scope.USER)] = Field(
        default=ZoneInfo("UTC"), title="Timezone", description="Display zone."
    )
    shown: Annotated[bool, Public()] = Field(
        default=True, title="Shown", description="Public only."
    )


def test_descriptors_carry_the_discovered_facts() -> None:
    """Key, scope, title, default, env name and schema come from the field."""
    catalogue = build_catalogue(
        discover([BackupSettings, SchedulerSettings]),
        {BackupSettings: BackupSettings(), SchedulerSettings: SchedulerSettings()},
    )
    keep = catalogue.descriptor("scheduler.run_history_per_job")
    assert keep.scope is SettingScope.INSTANCE
    assert (keep.title, keep.default) == ("Runs kept per task", 100)
    assert keep.env_name == "MENAGERIST_SCHEDULER_RUN_HISTORY_PER_JOB"
    assert keep.schema["minimum"] == 1
    assert catalogue.descriptor("backup.schedule").schema["x-menagerist"] == {
        "kind": "cron"
    }


def test_a_field_set_in_the_environment_is_pinned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An env var locks the setting and reports the variable and value."""
    monkeypatch.setenv("MENAGERIST_SCHEDULER_RUN_HISTORY_PER_JOB", "30")
    catalogue = build_catalogue(
        discover([BackupSettings, SchedulerSettings]),
        {BackupSettings: BackupSettings(), SchedulerSettings: SchedulerSettings()},
    )
    pin = catalogue.pin("scheduler.run_history_per_job")
    assert pin is not None
    assert (pin.env_name, pin.value) == ("MENAGERIST_SCHEDULER_RUN_HISTORY_PER_JOB", 30)
    assert catalogue.pin("backup.schedule") is None


def test_an_empty_schedule_in_the_environment_is_a_pin_that_turns_it_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`MENAGERIST_BACKUP_SCHEDULE=` locks the job off rather than being ignored."""
    monkeypatch.setenv("MENAGERIST_BACKUP_SCHEDULE", "")
    catalogue = build_catalogue(
        discover([BackupSettings, SchedulerSettings]),
        {BackupSettings: BackupSettings(), SchedulerSettings: SchedulerSettings()},
    )
    pin = catalogue.pin("backup.schedule")
    assert pin is not None
    assert pin.value == ""


def test_a_value_given_in_code_is_not_a_deployment_pin() -> None:
    """Only env, dotenv and secret-file values lock a setting."""
    settings = SchedulerSettings(run_history_per_job=9)
    catalogue = build_catalogue(
        discover([SchedulerSettings]), {SchedulerSettings: settings}
    )
    assert catalogue.pin("scheduler.run_history_per_job") is None


def test_validation_uses_the_fields_own_constraints() -> None:
    """Zero is refused for the run quota and a schedule must be valid cron."""
    catalogue = build_catalogue(
        discover([BackupSettings, SchedulerSettings]),
        {BackupSettings: BackupSettings(), SchedulerSettings: SchedulerSettings()},
    )
    assert catalogue.normalise("scheduler.run_history_per_job", 5) == 5
    with pytest.raises(InvalidSettingValueError):
        catalogue.normalise("scheduler.run_history_per_job", 0)
    with pytest.raises(InvalidSettingValueError, match="cron"):
        catalogue.normalise("backup.schedule", "not a schedule")
    assert catalogue.normalise("backup.schedule", "") == ""


def test_public_only_fields_are_left_out_and_rich_types_round_trip() -> None:
    """A ZoneInfo is stored as its key and read back as a ZoneInfo."""
    catalogue = build_catalogue(discover([Display]), {Display: Display()})
    assert [d.key for d in catalogue.descriptors(SettingScope.USER)] == [
        "display.timezone"
    ]
    assert catalogue.descriptors(SettingScope.INSTANCE) == []
    assert catalogue.normalise("display.timezone", "Europe/London") == "Europe/London"
    assert catalogue.to_python("display.timezone", "Europe/London") == ZoneInfo(
        "Europe/London"
    )
    assert catalogue.descriptor("display.timezone").default == "UTC"


def test_the_deployment_catalogue_lists_the_registered_settings() -> None:
    """The real catalogue is built from the cached settings of every group."""
    keys = {d.key for d in deployment_catalogue().descriptors(SettingScope.INSTANCE)}
    assert keys >= {
        "backup.schedule",
        "scheduler.run_history_per_job",
    }
