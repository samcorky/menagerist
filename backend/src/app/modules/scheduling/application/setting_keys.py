"""The tunable settings this module reads."""

from app.shared_kernel.settings import SettingKey

RUN_HISTORY_PER_JOB = SettingKey[int]("scheduler.run_history_per_job")
