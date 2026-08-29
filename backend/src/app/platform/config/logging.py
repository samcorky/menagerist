from functools import lru_cache

from app.platform.config._base import MenageristBaseSettings


class LoggingSettings(MenageristBaseSettings):
    """Logging settings."""

    log_level: str = "INFO"
    log_json: bool = False


@lru_cache(maxsize=1)
def get_logging_settings() -> LoggingSettings:
    """Return the cached logging settings."""
    return LoggingSettings()
