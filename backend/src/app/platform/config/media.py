from functools import lru_cache
from pathlib import Path

from app.platform.config._base import MenageristBaseSettings


class MediaSettings(MenageristBaseSettings):
    """Configuration for the media module."""

    media_storage_path: Path = Path("/data/media")
    staged_ttl_hours: int = 24
    orphaned_ttl_hours: int = 72
    max_upload_size: int = 100 * 1024 * 1024


@lru_cache(maxsize=1)
def get_media_settings() -> MediaSettings:
    """Return the cached media settings."""
    return MediaSettings()
