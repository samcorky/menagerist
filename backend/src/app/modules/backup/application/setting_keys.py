"""The tunable settings this module reads."""

from app.shared_kernel.settings import SettingKey

KEEP_LAST = SettingKey[int]("backup.keep_last")
USER_EXPORT_TTL_HOURS = SettingKey[int]("backup.user_export_ttl_hours")
