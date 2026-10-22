from functools import lru_cache
from pathlib import Path

from pydantic import Field

from app.platform.config._base import MenageristBaseSettings


class BackupSettings(MenageristBaseSettings):
    """Instance backup storage, retention and upload limits."""

    backup_path: Path = Field(
        default=Path("/data/backups"),
        description="Directory used to store instance backup archives.",
    )
    user_export_ttl_hours: int = Field(
        default=24,
        gt=0,
        validation_alias="MENAGERIST_USER_EXPORT_TTL_HOURS",
        description="Hours to retain a person's downloadable data export.",
    )
    before_migrate: bool = Field(
        default=True,
        validation_alias="MENAGERIST_BACKUP_BEFORE_MIGRATE",
        description=(
            "Create a backup before applying database migrations. Enabled by default."
        ),
    )
    keep_last: int = Field(
        default=7,
        ge=1,
        validation_alias="MENAGERIST_BACKUP_KEEP_LAST",
        description="Minimum number of ordinary backups to retain.",
    )
    pre_migration_keep: int = Field(
        default=3,
        ge=1,
        validation_alias="MENAGERIST_BACKUP_PRE_MIGRATION_KEEP",
        description="Minimum number of pre-migration backups to retain.",
    )
    max_upload_size: int = Field(
        default=8 * 1024 * 1024 * 1024,
        gt=0,
        validation_alias="MENAGERIST_BACKUP_MAX_UPLOAD_SIZE",
        description="Maximum accepted backup archive upload size in bytes.",
    )


@lru_cache(maxsize=1)
def get_backup_settings() -> BackupSettings:
    """Return the cached backup settings."""
    return BackupSettings()
