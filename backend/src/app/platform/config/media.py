from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field

from app.platform.config._base import MenageristBaseSettings
from app.platform.config._markers import Tunable
from app.platform.config._types import Cron  # noqa: TC001 - pydantic resolves this at runtime


class MediaSettings(MenageristBaseSettings, group="media"):
    """Configuration for the media module."""

    storage_path: Path = Field(
        default=Path("/data/media"),
        description="Directory used to store uploaded media and generated assets.",
    )
    cleanup_schedule: Annotated[
        Cron,
        Field(
            title="Unused uploads clean-up schedule",
            description=(
                "Cron expression for removing expired unattached and unreferenced "
                + "media in the instance timezone. Empty disables the job."
            ),
        ),
        Tunable(),
    ] = "30 * * * *"
    stray_files_schedule: Annotated[
        Cron,
        Field(
            title="Leftover files clean-up schedule",
            description=(
                "Cron expression for removing stored files that no upload refers to, "
                + "in the instance timezone. Empty disables the job."
            ),
        ),
        Tunable(),
    ] = "45 3 * * 0"
    staged_ttl_hours: int = Field(
        default=24,
        ge=1,
        description="Hours to keep media uploads that have not been attached.",
    )
    orphaned_ttl_hours: int = Field(
        default=72,
        ge=1,
        description="Hours to keep media files that are no longer referenced.",
    )
    max_upload_size: int = Field(
        default=100 * 1024 * 1024,
        gt=0,
        description="Maximum accepted media upload size in bytes.",
    )


@lru_cache(maxsize=1)
def get_media_settings() -> MediaSettings:
    """Return the cached media settings."""
    return MediaSettings()
