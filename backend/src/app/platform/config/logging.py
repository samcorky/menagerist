from enum import StrEnum
from functools import lru_cache

from app.platform.config._base import MenageristBaseSettings


class LogLevel(StrEnum):
    """Python logging levels, accepting either upper- or lowercase values."""

    CRITICAL = "CRITICAL"
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"
    DEBUG = "DEBUG"
    NOTSET = "NOTSET"

    @classmethod
    def _missing_(cls, value: object) -> LogLevel | None:
        if isinstance(value, str):
            return cls.__members__.get(value.upper())
        return None


class LoggingSettings(MenageristBaseSettings):
    """Logging settings."""

    log_level: LogLevel = LogLevel.INFO
    sqlalchemy_log_level: LogLevel = LogLevel.WARNING
    log_json: bool = False
    access_log: bool = True


@lru_cache(maxsize=1)
def get_logging_settings() -> LoggingSettings:
    """Return the cached logging settings."""
    return LoggingSettings()
