from enum import StrEnum
from functools import lru_cache

from pydantic import Field

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


class LoggingSettings(MenageristBaseSettings, group="log"):
    """Logging settings."""

    level: LogLevel = Field(
        default=LogLevel.INFO,
        description="Minimum severity emitted by Menagerist application loggers.",
    )
    sqlalchemy_level: LogLevel = Field(
        default=LogLevel.WARNING,
        description="Minimum severity emitted by SQLAlchemy's engine logger.",
    )
    json_output: bool = Field(
        default=False,
        description="Emit structured logs as JSON instead of the development format.",
    )
    access: bool = Field(
        default=True,
        description="Emit HTTP access log entries for application requests.",
    )


@lru_cache(maxsize=1)
def get_logging_settings() -> LoggingSettings:
    """Return the cached logging settings."""
    return LoggingSettings()
