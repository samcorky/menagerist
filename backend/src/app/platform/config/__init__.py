from app.platform.config._base import MenageristBaseSettings
from app.platform.config.api import ApiSettings, get_api_settings
from app.platform.config.backup import BackupSettings, get_backup_settings
from app.platform.config.database import DatabaseSettings, get_database_settings
from app.platform.config.identity import IdentitySettings, get_identity_settings
from app.platform.config.identity_cli import (
    IdentityCliSettings,
    get_identity_cli_settings,
)
from app.platform.config.logging import LoggingSettings, LogLevel, get_logging_settings
from app.platform.config.media import MediaSettings, get_media_settings
from app.platform.config.release import ReleaseSettings, get_release_settings
from app.platform.config.retention import RetentionSettings, get_retention_settings
from app.platform.config.scheduler import SchedulerSettings, get_scheduler_settings
from app.platform.config.server import ServerSettings, get_server_settings

# Settings that describe a running instance; the CLI-only identity settings
# are read fresh by the CLI and are not part of it.
INSTANCE_SETTINGS = (
    get_api_settings,
    get_backup_settings,
    get_database_settings,
    get_identity_settings,
    get_logging_settings,
    get_media_settings,
    get_release_settings,
    get_retention_settings,
    get_scheduler_settings,
    get_server_settings,
)

# Every deployment settings class, including the CLI-only ones. The generated
# reference lists all of them; the settings page keeps only their tunable fields.
ALL_SETTINGS: tuple[type[MenageristBaseSettings], ...] = (
    ApiSettings,
    BackupSettings,
    DatabaseSettings,
    IdentitySettings,
    IdentityCliSettings,
    LoggingSettings,
    MediaSettings,
    ReleaseSettings,
    RetentionSettings,
    SchedulerSettings,
    ServerSettings,
)

__all__ = [
    "ALL_SETTINGS",
    "INSTANCE_SETTINGS",
    "ApiSettings",
    "BackupSettings",
    "DatabaseSettings",
    "IdentityCliSettings",
    "IdentitySettings",
    "LogLevel",
    "LoggingSettings",
    "MediaSettings",
    "MenageristBaseSettings",
    "ReleaseSettings",
    "RetentionSettings",
    "SchedulerSettings",
    "ServerSettings",
    "get_api_settings",
    "get_backup_settings",
    "get_database_settings",
    "get_identity_cli_settings",
    "get_identity_settings",
    "get_logging_settings",
    "get_media_settings",
    "get_release_settings",
    "get_retention_settings",
    "get_scheduler_settings",
    "get_server_settings",
]
