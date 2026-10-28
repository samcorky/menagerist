"""Every setting the code reads live must be a tunable the settings module serves."""

from app.entrypoints.cli.backup_jobs import LIVE_SCHEDULES
from app.modules.backup.application.setting_keys import KEEP_LAST, USER_EXPORT_TTL_HOURS
from app.modules.scheduling.application.setting_keys import RUN_HISTORY_PER_JOB
from app.platform.config import SETTING_GROUPS
from app.platform.config._discovery import discover

CODE_KEYS = {
    RUN_HISTORY_PER_JOB.key,
    KEEP_LAST.key,
    USER_EXPORT_TTL_HOURS.key,
    *LIVE_SCHEDULES,
}


def test_every_key_the_code_reads_is_a_tunable_setting() -> None:
    """A renamed field or a dropped marker would otherwise fail only at runtime."""
    tunable = {spec.key for spec in discover(SETTING_GROUPS) if spec.tunable}
    assert tunable >= CODE_KEYS


def test_live_schedules_are_cron_settings() -> None:
    """A live schedule key is a cron string, which turns the job off when empty."""
    specs = {spec.key: spec for spec in discover(SETTING_GROUPS)}
    for key in LIVE_SCHEDULES:
        assert specs[key].schema["x-menagerist"] == {"kind": "cron"}
