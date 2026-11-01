from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field

from app.platform.config._base import MenageristBaseSettings
from app.platform.config._markers import Tunable
from app.platform.config._types import Cron, Hours  # noqa: TC001 - pydantic resolves these at runtime


class BackupSettings(MenageristBaseSettings, group="backup"):
    """Instance backup storage, retention and upload limits."""

    path: Path = Field(
        default=Path("/data/backups"),
        description="Directory used to store instance backup archives.",
    )
    user_export_ttl_hours: Annotated[
        Hours,
        Field(
            title="Data export lifetime",
            description="Hours to retain a person's downloadable data export.",
        ),
        Tunable(),
    ] = 24
    before_migrate: bool = Field(
        default=True,
        description=(
            "Create a backup before applying database migrations. Enabled by default."
        ),
    )
    keep_last: Annotated[
        int,
        Field(
            ge=1,
            title="Backups to keep",
            description="Minimum number of ordinary backups to retain.",
        ),
        Tunable(),
    ] = 7
    pre_migration_keep: int = Field(
        default=3,
        ge=1,
        description="Minimum number of pre-migration backups to retain.",
    )
    schedule: Annotated[
        Cron,
        Field(
            title="Backup schedule",
            description=(
                "Cron expression for scheduled backups in the instance timezone. "
                + "Empty disables scheduled backups; "
                + "each success is followed by retention."
            ),
        ),
        Tunable(),
    ] = "0 3 * * *"
    prune_exports_schedule: Annotated[
        Cron,
        Field(
            title="Export clean-up schedule",
            description=(
                "Cron expression for expiring downloadable data exports. "
                + "Empty disables the job."
            ),
        ),
        Tunable(),
    ] = "0 * * * *"
    max_upload_size: int = Field(
        default=8 * 1024 * 1024 * 1024,
        gt=0,
        description="Maximum accepted backup archive upload size in bytes.",
    )


@lru_cache(maxsize=1)
def get_backup_settings() -> BackupSettings:
    """Return the cached backup settings."""
    return BackupSettings()
