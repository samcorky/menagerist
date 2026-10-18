from functools import lru_cache
from pathlib import Path

from pydantic import Field

from app.platform.config._base import MenageristBaseSettings


class BackupSettings(MenageristBaseSettings):
    """Instance backup storage, retention and upload limits.

    Setup uploads accept archives up to 8 GiB by default.
    """

    backup_path: Path = Path("/data/backups")
    before_migrate: bool = Field(
        default=False, validation_alias="MENAGERIST_BACKUP_BEFORE_MIGRATE"
    )
    keep_last: int = Field(default=7, validation_alias="MENAGERIST_BACKUP_KEEP_LAST")
    pre_migration_keep: int = Field(
        default=3, validation_alias="MENAGERIST_BACKUP_PRE_MIGRATION_KEEP"
    )
    max_upload_size: int = Field(
        default=8 * 1024 * 1024 * 1024,
        validation_alias="MENAGERIST_BACKUP_MAX_UPLOAD_SIZE",
    )


@lru_cache(maxsize=1)
def get_backup_settings() -> BackupSettings:
    """Return the cached backup settings."""
    return BackupSettings()
